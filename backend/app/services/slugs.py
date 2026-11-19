import re
import unicodedata


def slugify(value: str, max_length: int = 60) -> str:
    """« Cabinet Kouassi & Associés » -> « cabinet-kouassi-associes »."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "organisation"
