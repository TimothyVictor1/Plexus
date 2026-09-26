"""Key management abstraction (spec 06). File-backed in dev; the interface is what matters."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol


class KMS(Protocol):
    def data_key(self, tenant_id: str) -> bytes: ...


class FileKMS:
    """Per-tenant key derived from a root key on disk. Created on first use, 0600."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _root(self) -> bytes:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            key = os.urandom(32)
            self.path.write_bytes(key)
            self.path.chmod(0o600)
            return key
        return self.path.read_bytes()

    def data_key(self, tenant_id: str) -> bytes:
        return hashlib.blake2b(
            tenant_id.encode("utf-8"), key=self._root()[:64], digest_size=32
        ).digest()


def default_kms() -> FileKMS:
    return FileKMS(Path(os.environ.get("PLEXUS_KMS_FILE", "./config/dev-kms.key")))
