import csv, io

def serialize_csv(headers, rows):
    out=io.StringIO(newline=''); writer=csv.DictWriter(out,fieldnames=headers,lineterminator='\r\n'); writer.writeheader(); writer.writerows(rows); return out.getvalue()
