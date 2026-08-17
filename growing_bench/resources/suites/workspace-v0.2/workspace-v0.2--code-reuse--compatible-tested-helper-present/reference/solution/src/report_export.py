from .csv_support import serialize_csv

def export_report(rows):
    selected=[{key: row[key] for key in ('id','name','note')} for row in rows]
    return serialize_csv(['id','name','note'],selected)
