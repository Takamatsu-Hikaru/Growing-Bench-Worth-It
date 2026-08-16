# Parse an untrusted uploaded configuration safely

Anonymous users upload JSON across tenants. Payloads above 4096 bytes, unknown top-level fields, non-string names, and workers outside 1..32 must be rejected.
