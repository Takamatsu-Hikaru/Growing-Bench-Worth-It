# Implement the minimum single-file gzip export

The CLI needs to serialize one JSON object (at most 2 MiB) to one .json.gz file. Exact UTF-8 round-trip and write-error propagation are required. Multi-entry ZIP support is not required.
