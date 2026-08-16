import json
paper=json.load(open('evidence.json',encoding='utf-8'))
results=json.load(open('data/results.json',encoding='utf-8'))
assert paper['records']==results['records']
assert all(row['evidence_id'] and len(row['statement'])>=20 for row in paper['records'])
print(json.dumps({'verified':True,'record_count':len(paper['records']),'evidence_ids':[row['evidence_id'] for row in paper['records']]}))
