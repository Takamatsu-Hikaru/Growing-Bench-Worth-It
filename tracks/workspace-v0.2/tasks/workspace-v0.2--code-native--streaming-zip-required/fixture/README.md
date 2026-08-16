# Implement bounded-memory multi-entry ZIP export

The export may contain many JSON or binary files totaling several GiB. A standards-compatible ZIP, deterministic caller order, bounded memory, unsafe-name rejection, and write-error propagation are required.
