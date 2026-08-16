# Add bounded HTTP retry without unrelated infrastructure

request_with_retry(call) should retry TimeoutError twice, then return or re-raise. No deployment manifests or cluster integration are part of this task.
