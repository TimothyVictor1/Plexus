"""Key management abstraction (spec 06). File-backed in dev; the interface is what matters."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
from pathlib import Path
from typing import Protocol

MIN_ROOT_BYTES = 32


class KMS(Protocol):
    def data_key(self, tenant_id: str) -> bytes: ...


class RootKeyError(ValueError):
    """The configured root key is missing or too weak to derive from."""


def _derive(root: bytes, tenant_id: str) -> bytes:
    return hashlib.blake2b(tenant_id.encode("utf-8"), key=root[:64], digest_size=32).digest()


class FileKMS:
    """Per-tenant key derived from a root key on disk. Created on first use, 0600.

    For a machine with a durable disk. Creating the key on first use is a convenience for local
    development; see EnvKMS for anywhere the filesystem does not survive a restart.
    """

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
        return _derive(self._root(), tenant_id)


class EnvKMS:
    """Per-tenant key derived from a root key held in the environment.

    Required wherever the filesystem is not durable. A serverless host has no disk to keep a key
    on, and a key invented per cold start would be worse than no key at all: this one root key
    decides both how personal details are tokenised and how the vault is encrypted, so a
    different one each time would derive different tokens for the same person and leave
    everything already stored unreadable.

    It must therefore be the same value that was used when the database was seeded.
    """

    def __init__(self, root: bytes) -> None:
        if len(root) < MIN_ROOT_BYTES:
            msg = (
                f"root key is {len(root)} bytes; at least {MIN_ROOT_BYTES} are needed."
                ' Generate one with: python -c "import secrets;print(secrets.token_hex(32))"'
            )
            raise RootKeyError(msg)
        self._root_key = root

    def data_key(self, tenant_id: str) -> bytes:
        return _derive(self._root_key, tenant_id)


def decode_root_key(raw: str) -> bytes:
    """Read a root key written as hex, as base64, or as raw text.

    A key travels through an environment variable, a secret store and a copy-paste before it
    gets here, so accept the spellings it plausibly arrives in rather than making the operator
    guess which one is wanted.

    A decoding is only used when it yields enough bytes to derive from. Without that rule a
    40-character passphrase that happens to be made of base64 characters would decode to 30
    bytes and be refused as too short, which tells the operator nothing useful about a key they
    typed at the right length.
    """

    def from_hex(text: str) -> bytes:
        return binascii.unhexlify(text)

    def from_base64(text: str) -> bytes:
        return base64.b64decode(text, validate=True)

    text = raw.strip()
    for decode in (from_hex, from_base64):
        try:
            decoded = decode(text)
        except (binascii.Error, ValueError):
            continue
        if len(decoded) >= MIN_ROOT_BYTES:
            return decoded
    return text.encode("utf-8")


def default_kms() -> KMS:
    """The environment's key if there is one, otherwise the key file.

    The environment wins, because a host that sets it is telling us its disk is not somewhere
    to keep a key.
    """
    raw = os.environ.get("PLEXUS_KMS_KEY", "").strip()
    if raw:
        return EnvKMS(decode_root_key(raw))
    return FileKMS(Path(os.environ.get("PLEXUS_KMS_FILE", "./config/dev-kms.key")))
