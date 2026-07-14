"""Shared helpers for the parent-child scripts."""
import re


def normalize_domain(raw):
    """Lowercase a domain/URL down to a bare comparable domain (no scheme, www, path)."""
    if not raw:
        return ""
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0].split("?")[0]
    return d.strip()


def find_column(fieldnames, keywords):
    """Return the first fieldname that contains any of the given keywords (case-insensitive)."""
    for fn in fieldnames or []:
        low = fn.lower()
        for kw in keywords:
            if kw in low:
                return fn
    return None
