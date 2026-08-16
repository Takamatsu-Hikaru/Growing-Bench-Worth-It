# Add CSV export by reusing the existing serializer

src/csv_support.py is already used by three routes and covers commas, quotes, CRLF, Unicode, header order, and final CRLF. Add export_report(rows) in src/report_export.py for id,name,note.
