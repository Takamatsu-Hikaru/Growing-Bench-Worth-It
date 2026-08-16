def request_with_retry(call):
    for attempt in range(3):
        try: return call()
        except TimeoutError:
            if attempt==2: raise
