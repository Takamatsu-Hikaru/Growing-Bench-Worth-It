import re


def normalize_slug(value: str) -> str:
    """Canonical repository policy for user-facing target labels."""
    compact = re.sub(r"[^a-z0-9]+", "-", value.strip().casefold())
    return compact.strip("-")
