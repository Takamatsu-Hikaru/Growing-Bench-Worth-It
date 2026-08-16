from .slug import normalize_slug


def create_target(label: str) -> str:
    return f"targets/{normalize_slug(label)}"
