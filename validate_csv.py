import csv

with open('dataset/output.csv', 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    headers = next(reader)
    rows = list(reader)

print(f'Row count: {len(rows)}')
print(f'Column count: {len(headers)}')

user_ids = [r[0] for r in rows]
duplicates = len(user_ids) - len(set(user_ids))
print(f'Duplicate claim ids: {duplicates}')

req_cols = ["user_id","image_paths","user_claim","claim_object","evidence_standard_met","evidence_standard_met_reason","risk_flags","issue_type","object_part","claim_status","claim_status_justification","supporting_image_ids","valid_image","severity"]
missing_cols = [c for c in req_cols if c not in headers]
print(f'Missing required columns: {missing_cols}')
