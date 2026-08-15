import csv,json
from collections import Counter
rows=list(csv.DictReader(open('data/annotations.csv',encoding='utf-8')))
notes=list(csv.DictReader(open('data/ambiguity_notes.csv',encoding='utf-8')))
a=[r['annotator_a'] for r in rows]; b=[r['annotator_b'] for r in rows]
names=set(a)|set(b); n=len(rows)
po=sum(x==y for x,y in zip(a,b))/n
pe=sum((a.count(x)/n)*(b.count(x)/n) for x in names)
k=(po-pe)/(1-pe)
analysis=json.load(open('data/analysis.json',encoding='utf-8'))
assert n==94 and len({r['item_id'] for r in rows})==94 and len({r['input_summary'] for r in rows})==94
assert Counter(r['adjudicated_category'] for r in rows)==Counter(analysis['category_counts'])
assert len(notes)==29 and {r['item_id'] for r in notes}=={r['item_id'] for r in rows if r['adjudicated_category']=='label_ambiguity'}
assert round(k,6)==analysis['cohen_kappa']
print({'rows':n,'ambiguity_notes':len(notes),'agreement':po,'kappa':k})
