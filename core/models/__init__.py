"""Model router (spec 09). Vendor SDKs are imported only under core.models.providers."""

from core.models.router import Router, get_router
from core.models.types import Completion, Message, ModelId, Role, VendorSeparationError

__all__ = [
    "Completion",
    "Message",
    "ModelId",
    "Role",
    "Router",
    "VendorSeparationError",
    "get_router",
]
