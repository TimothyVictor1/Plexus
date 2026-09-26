"""Vendor providers behind the router. The ONLY package that may import a vendor SDK."""

from core.models.providers.local import LocalProvider

__all__ = ["LocalProvider"]
