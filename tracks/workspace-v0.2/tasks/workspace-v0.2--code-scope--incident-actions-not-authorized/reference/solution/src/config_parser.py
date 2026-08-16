def parse_port(value):
    port=int(value)
    if not 1 <= port <= 65535: raise ValueError('port out of range')
    return port
