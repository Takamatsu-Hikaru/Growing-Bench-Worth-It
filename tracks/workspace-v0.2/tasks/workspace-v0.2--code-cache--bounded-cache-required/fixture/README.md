# Add a bounded cache to a measured hot path

load_catalog is called thousands of times per request on the same file. Use one-entry mtime-aware caching; edits must invalidate the cached value.
