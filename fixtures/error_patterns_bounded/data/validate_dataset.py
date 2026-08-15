import csv, json
from collections import Counter
rows=list(csv.DictReader(open('data/annotations.csv', encoding='utf-8')))
assert len(rows)==94
assert len({r['item_id'] for r in rows})==94
assert len({r['ticket_cluster_id'] for r in rows})==94
assert len({r['input_summary'] for r in rows})==94
counts=Counter(r['adjudicated_category'] for r in rows)
expected=json.load(open('data/analysis.json', encoding='utf-8'))['category_counts']
assert dict(counts)==expected
print({'rows':len(rows),'unique_items':94,'unique_clusters':94,'counts':dict(counts)})
