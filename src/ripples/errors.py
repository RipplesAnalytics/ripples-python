from __future__ import annotations


class RipplesError(Exception):
    """Base exception for Ripples SDK errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
