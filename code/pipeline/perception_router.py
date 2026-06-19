import logging
import time
from typing import Any, Mapping
from dataclasses import dataclass

from schemas import ImageRef
from google.genai import errors as genai_errors
import openai

# Setup logger for perception specifically
perception_logger = logging.getLogger("perception")
perception_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("logs/perception.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
perception_logger.addHandler(file_handler)

import json
from datetime import datetime, timezone
import os

@dataclass
class KeyState:
    last_request_time: float = 0.0
    cooldown_until: float = 0.0
    fatal_failures: int = 0
    transient_failures: int = 0

class PerceptionRouter:
    """Routes requests to NVIDIA, falling back to Gemini Pool, then Mock."""
    
    def __init__(self, nvidia_client, gemini_clients: list, mock_client):
        self.nvidia_client = nvidia_client
        self.gemini_clients = gemini_clients
        self.mock_client = mock_client
        self.current_key_idx = 0
        self.key_states = [KeyState() for _ in gemini_clients]
        self.nvidia_state = KeyState()
        
        self.MAX_FATAL_FAILURES = 2
        self.MAX_TRANSIENT_RETRIES = 1
        self.MIN_DELAY_BETWEEN_REQUESTS = 5.0  # 5 seconds per key for Gemini

        self.cache_file = "logs/perception_cache.jsonl"
        self.cache = {}
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, start=1):
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            self.cache[entry["image"]] = entry["response"]
                        except json.JSONDecodeError:
                            perception_logger.warning(f"cache_corruption_detected line_number={i}")
                            continue

    def _save_to_cache(self, image_path: str, provider: str, response: Mapping[str, Any]):
        if image_path not in self.cache:
            self.cache[image_path] = response
            entry = {
                "image": image_path,
                "provider": provider,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response": response
            }
            with open(self.cache_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            perception_logger.info(f"cache_saved image={image_path}")

    def analyze_image(self, image: ImageRef) -> Mapping[str, Any]:
        if image.image_path in self.cache:
            perception_logger.info(f"cache_hit image={image.image_path}")
            return self.cache[image.image_path]
            
        perception_logger.info(f"cache_miss image={image.image_path}")
        result, provider = self._analyze_image_internal(image)
        self._save_to_cache(image.image_path, provider, result)
        return result

    def _analyze_image_internal(self, image: ImageRef) -> tuple[Mapping[str, Any], str]:
        """Try NVIDIA first. If it fails API-wise, fallback to Gemini pool. Fallback to mock on exhaustion."""
        now = time.time()
        
        # 1. Try NVIDIA
        if self.nvidia_client and self.nvidia_state.fatal_failures <= self.MAX_FATAL_FAILURES:
            if now >= self.nvidia_state.cooldown_until:
                attempt = self.nvidia_state.transient_failures + 1
                try:
                    perception_logger.info(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} image={image.image_path}"
                    )
                    result = self.nvidia_client.analyze_image(image)
                    self.nvidia_state.transient_failures = 0
                    return result, "NVIDIA"
                except openai.RateLimitError as e:
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} failure_reason={reason} status_code=429"
                    )
                    self.nvidia_state.cooldown_until = time.time() + 60.0
                except (openai.APIError, openai.APIConnectionError, openai.Timeout) as e:
                    reason = str(e).replace("\n", " ")
                    status = getattr(e, 'status_code', 500)
                    perception_logger.warning(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} failure_reason={reason} status_code={status}"
                    )
                    if status >= 500:
                        self.nvidia_state.transient_failures += 1
                        if self.nvidia_state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                            self.nvidia_state.fatal_failures += 1
                    else:
                        self.nvidia_state.fatal_failures += 1
                except Exception as e:
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} failure_reason={reason}"
                    )
                    self.nvidia_state.transient_failures += 1
                    if self.nvidia_state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                        self.nvidia_state.fatal_failures += 1

        # 2. Try Gemini Pool
        if self.gemini_clients:
            while True:
                # Check if all keys are permanently dead
                if all(state.fatal_failures > self.MAX_FATAL_FAILURES for state in self.key_states):
                    perception_logger.warning("All Gemini keys permanently exhausted. Falling back to Mock.")
                    break

                client = self.gemini_clients[self.current_key_idx]
                state = self.key_states[self.current_key_idx]
                
                if state.fatal_failures > self.MAX_FATAL_FAILURES:
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    continue
                    
                now = time.time()
                if now < state.cooldown_until:
                    # Need to check other keys. If all alive keys are cooling down, we must sleep.
                    alive_keys = [s for s in self.key_states if s.fatal_failures <= self.MAX_FATAL_FAILURES]
                    if all(now < s.cooldown_until for s in alive_keys):
                        # Don't sleep if NVIDIA is cooling down but might be ready sooner?
                        if self.nvidia_client and self.nvidia_state.fatal_failures <= self.MAX_FATAL_FAILURES:
                            if self.nvidia_state.cooldown_until <= min(s.cooldown_until for s in alive_keys):
                                sleep_time = self.nvidia_state.cooldown_until - now
                                if sleep_time > 0:
                                    time.sleep(sleep_time)
                                # Break out to retry NVIDIA
                                return self.analyze_image(image)

                        sleep_time = min(s.cooldown_until for s in alive_keys) - now
                        if sleep_time > 0:
                            perception_logger.info(f"All keys cooling down. Sleeping for {sleep_time:.2f}s")
                            time.sleep(sleep_time)
                    else:
                        self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    continue

                # Enforce per-key delay
                time_since_last = now - state.last_request_time
                if time_since_last < self.MIN_DELAY_BETWEEN_REQUESTS:
                    sleep_time = self.MIN_DELAY_BETWEEN_REQUESTS - time_since_last
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    
                state.last_request_time = time.time()
                attempt = state.transient_failures + 1

                try:
                    perception_logger.info(
                        f"provider_used=Gemini model_used=gemini-2.5-flash provider_key_index={self.current_key_idx} "
                        f"attempt_number={attempt} image={image.image_path}"
                    )
                    result = client.analyze_image(image)
                    
                    # Success
                    state.transient_failures = 0
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    return result, "Gemini"
                    
                except genai_errors.APIError as e:
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=Gemini model_used=gemini-2.5-flash provider_key_index={self.current_key_idx} "
                        f"attempt_number={attempt} failure_reason={reason} status_code={e.code}"
                    )
                    
                    if e.code == 429:
                        # Rate limit: cooldown 60s
                        state.cooldown_until = time.time() + 60.0
                        self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    elif e.code and e.code >= 500:
                        # 5xx error: transient backoff
                        state.transient_failures += 1
                        if state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                            state.fatal_failures += 1
                            state.transient_failures = 0
                        else:
                            time.sleep(2 ** state.transient_failures)
                    else:
                        # Fatal API error (e.g., auth, bad request)
                        state.fatal_failures += 1
                        
                except Exception as e:
                    # Malformed JSON or other fatal error
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=Gemini model_used=gemini-2.5-flash provider_key_index={self.current_key_idx} "
                        f"attempt_number={attempt} failure_reason={reason}"
                    )
                    state.transient_failures += 1
                    if state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                        state.fatal_failures += 1
                        state.transient_failures = 0
                    else:
                        time.sleep(2 ** state.transient_failures)
                        
        # 3. Fallback to Mock
        perception_logger.info(f"provider_used=Mock model_used=mock attempt_number=1 image={image.image_path}")
        return self.mock_client.analyze_image(image), "Mock"

    def analyze_images(self, images: list[ImageRef]) -> list[Mapping[str, Any]]:
        results = []
        missing_images = []
        for img in images:
            if img.image_path in self.cache:
                perception_logger.info(f"cache_hit image={img.image_path}")
            else:
                perception_logger.info(f"cache_miss image={img.image_path}")
                missing_images.append(img)
                
        if missing_images:
            new_results, provider = self._analyze_images_internal(missing_images)
            for img, res in zip(missing_images, new_results):
                self._save_to_cache(img.image_path, provider, res)
                
        final_results = []
        for img in images:
            final_results.append(self.cache[img.image_path])
        return final_results

    def _analyze_images_internal(self, images: list[ImageRef]) -> tuple[list[Mapping[str, Any]], str]:
        now = time.time()
        images_str = ",".join([img.image_path for img in images])
        
        # 1. Try NVIDIA
        if self.nvidia_client and hasattr(self.nvidia_client, "analyze_images") and self.nvidia_state.fatal_failures <= self.MAX_FATAL_FAILURES:
            if now >= self.nvidia_state.cooldown_until:
                attempt = self.nvidia_state.transient_failures + 1
                try:
                    perception_logger.info(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} images={images_str}"
                    )
                    result = self.nvidia_client.analyze_images(images)
                    self.nvidia_state.transient_failures = 0
                    return result, "NVIDIA"
                except openai.RateLimitError as e:
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} failure_reason={reason} status_code=429"
                    )
                    self.nvidia_state.cooldown_until = time.time() + 60.0
                except (openai.APIError, openai.APIConnectionError, openai.Timeout) as e:
                    reason = str(e).replace("\n", " ")
                    status = getattr(e, 'status_code', 500)
                    perception_logger.warning(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} failure_reason={reason} status_code={status}"
                    )
                    if status >= 500:
                        self.nvidia_state.transient_failures += 1
                        if self.nvidia_state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                            self.nvidia_state.fatal_failures += 1
                    else:
                        self.nvidia_state.fatal_failures += 1
                except Exception as e:
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=NVIDIA model_used=meta/llama-3.2-11b-vision-instruct "
                        f"attempt_number={attempt} failure_reason={reason}"
                    )
                    self.nvidia_state.transient_failures += 1
                    if self.nvidia_state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                        self.nvidia_state.fatal_failures += 1

        # 2. Try Gemini Pool
        if self.gemini_clients:
            while True:
                # Check if all keys are permanently dead
                if all(state.fatal_failures > self.MAX_FATAL_FAILURES for state in self.key_states):
                    perception_logger.warning("All Gemini keys permanently exhausted. Falling back to Mock.")
                    break

                client = self.gemini_clients[self.current_key_idx]
                state = self.key_states[self.current_key_idx]
                
                if state.fatal_failures > self.MAX_FATAL_FAILURES:
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    continue
                    
                now = time.time()
                if now < state.cooldown_until:
                    # Need to check other keys. If all alive keys are cooling down, we must sleep.
                    alive_keys = [s for s in self.key_states if s.fatal_failures <= self.MAX_FATAL_FAILURES]
                    if all(now < s.cooldown_until for s in alive_keys):
                        # Don't sleep if NVIDIA is cooling down but might be ready sooner?
                        if self.nvidia_client and self.nvidia_state.fatal_failures <= self.MAX_FATAL_FAILURES:
                            if self.nvidia_state.cooldown_until <= min(s.cooldown_until for s in alive_keys):
                                sleep_time = self.nvidia_state.cooldown_until - now
                                if sleep_time > 0:
                                    time.sleep(sleep_time)
                                # Break out to retry NVIDIA
                                return self._analyze_images_internal(images)

                        sleep_time = min(s.cooldown_until for s in alive_keys) - now
                        if sleep_time > 0:
                            perception_logger.info(f"All keys cooling down. Sleeping for {sleep_time:.2f}s")
                            time.sleep(sleep_time)
                    else:
                        self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    continue

                # Enforce per-key delay
                time_since_last = now - state.last_request_time
                if time_since_last < self.MIN_DELAY_BETWEEN_REQUESTS:
                    sleep_time = self.MIN_DELAY_BETWEEN_REQUESTS - time_since_last
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    
                state.last_request_time = time.time()
                attempt = state.transient_failures + 1

                try:
                    perception_logger.info(
                        f"provider_used=Gemini model_used=gemini-2.5-flash provider_key_index={self.current_key_idx} "
                        f"attempt_number={attempt} images={images_str}"
                    )
                    result = client.analyze_images(images)
                    
                    # Success
                    state.transient_failures = 0
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    return result, "Gemini"
                    
                except genai_errors.APIError as e:
                    status = getattr(e, 'code', 500)
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=Gemini model_used=gemini-2.5-flash provider_key_index={self.current_key_idx} "
                        f"attempt_number={attempt} failure_reason={reason} status_code={status}"
                    )
                    if status == 429:
                        state.cooldown_until = time.time() + 60.0
                    elif status >= 500:
                        state.transient_failures += 1
                        if state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                            state.fatal_failures += 1
                    else:
                        state.fatal_failures += 1
                        
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    continue
                except Exception as e:
                    reason = str(e).replace("\n", " ")
                    perception_logger.warning(
                        f"provider_used=Gemini model_used=gemini-2.5-flash provider_key_index={self.current_key_idx} "
                        f"attempt_number={attempt} failure_reason={reason}"
                    )
                    state.transient_failures += 1
                    if state.transient_failures > self.MAX_TRANSIENT_RETRIES:
                        state.fatal_failures += 1
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.gemini_clients)
                    continue
                    
        # 3. Exhausted everything. Fall back to mock.
        perception_logger.info(f"provider_used=Mock attempt_number=1 images={images_str}")
        return [self.mock_client.analyze_image(img) for img in images], "Mock"
