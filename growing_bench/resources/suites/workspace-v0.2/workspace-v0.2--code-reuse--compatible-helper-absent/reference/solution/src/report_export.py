import csv, io

def export_report(rows):
    out=io.StringIO(newline=''); fields=['id','name','note']; writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\r\n'); writer.writeheader(); writer.writerows({key: row[key] for key in fields} for row in rows); return out.getvalue()
