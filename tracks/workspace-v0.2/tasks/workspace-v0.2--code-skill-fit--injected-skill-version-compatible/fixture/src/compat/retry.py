def retry_call(call, attempts=3):
    for index in range(attempts):
        try: return call()
        except TimeoutError:
            if index==attempts-1: raise
