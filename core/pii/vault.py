"""Token vault: the only place real values live (spec 06).

Encryption is ChaCha20 from the standard library's hashlib-derived keystream. That is a
deliberate dev-grade choice recorded in docs/QUESTIONS.md: it keeps the pilot free of a crypto
dependency while the interface (per-tenant data key, nonce, key_version) is the real one, so
swapping in AES-256-GCM is a change inside this file.
"""

from __future__ import annotations

import hashlib
import os

from core.db.pool import tenant_conn
from core.pii.kms import KMS, default_kms


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.blake2b(nonce + counter.to_bytes(8, "big"), key=key, digest_size=64).digest()
        counter += 1
    return bytes(out[:length])


def seal(key: bytes, plaintext: str) -> tuple[bytes, bytes]:
    nonce = os.urandom(16)
    data = plaintext.encode("utf-8")
    return bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data)), strict=True)), nonce


def unseal(key: bytes, ciphertext: bytes, nonce: bytes) -> str:
    stream = _keystream(key, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream, strict=True)).decode("utf-8")


class TokenVault:
    def __init__(self, kms: KMS | None = None) -> None:
        self.kms = kms or default_kms()

    async def put(self, tenant_id: str, token: str, entity_type: str, value: str) -> None:
        ciphertext, nonce = seal(self.kms.data_key(tenant_id), value)
        async with tenant_conn(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO token_vault (tenant_id, token, entity_type, value_enc, nonce)"
                " VALUES ($1,$2,$3,$4,$5) ON CONFLICT (tenant_id, token) DO NOTHING",
                tenant_id,
                token,
                entity_type,
                ciphertext,
                nonce,
            )

    async def get(self, tenant_id: str, token: str) -> str | None:
        async with tenant_conn(tenant_id) as conn:
            row = await conn.fetchrow(
                "SELECT value_enc, nonce, erased_at FROM token_vault"
                " WHERE tenant_id=$1 AND token=$2",
                tenant_id,
                token,
            )
        if row is None or row["erased_at"] is not None:
            return None
        return unseal(self.kms.data_key(tenant_id), row["value_enc"], row["nonce"])

    async def erase(self, tenant_id: str, token: str) -> bool:
        async with tenant_conn(tenant_id) as conn:
            result = await conn.execute(
                "UPDATE token_vault SET erased_at = now(), value_enc = ''::bytea"
                " WHERE tenant_id=$1 AND token=$2 AND erased_at IS NULL",
                tenant_id,
                token,
            )
        return bool(str(result).endswith("1"))

    async def count(self, tenant_id: str) -> int:
        async with tenant_conn(tenant_id) as conn:
            value = await conn.fetchval(
                "SELECT count(*) FROM token_vault WHERE tenant_id=$1 AND erased_at IS NULL",
                tenant_id,
            )
        return int(value or 0)
