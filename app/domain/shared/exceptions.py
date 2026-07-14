# AUDIT-2 FIXES: future-annotations-consistency
from __future__ import annotations


class DomainException(Exception):  # noqa: N818
    """Base for all domain exceptions. Maps to HTTP 500 unless a subclass overrides."""
