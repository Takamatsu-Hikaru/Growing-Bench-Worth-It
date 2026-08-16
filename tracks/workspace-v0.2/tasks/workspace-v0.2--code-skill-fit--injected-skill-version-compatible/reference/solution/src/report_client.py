from .compat.retry import retry_call

def fetch_report(call):
    return retry_call(call,attempts=3)
