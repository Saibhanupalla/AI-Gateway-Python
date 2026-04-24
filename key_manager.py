"""
API Key Management — Virtual Keys with at-rest encryption.

Stores provider API keys in the database encrypted with Fernet symmetric encryption.
Admins can add, rotate, and revoke keys per provider.
"""
import os
import logging
from typing import Optional, List
from cryptography.fernet import Fernet
from sqlmodel import select
from database import get_session, VirtualKey
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("ai_gateway.key_manager")

# Encryption key for at-rest key storage. Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Store in .env as ENCRYPTION_KEY
_ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")


def _get_fernet() -> Optional[Fernet]:
    if not _ENCRYPTION_KEY:
        logger.warning("ENCRYPTION_KEY not set — virtual keys will be stored in plaintext")
        return None
    return Fernet(_ENCRYPTION_KEY.encode())


def encrypt_key(plaintext: str) -> str:
    f = _get_fernet()
    if f:
        return f.encrypt(plaintext.encode()).decode()
    return plaintext


def decrypt_key(ciphertext: str) -> str:
    f = _get_fernet()
    if f:
        try:
            return f.decrypt(ciphertext.encode()).decode()
        except Exception:
            logger.error("Failed to decrypt key — returning raw value")
            return ciphertext
    return ciphertext


def store_virtual_key(
    provider: str,
    key_name: str,
    api_key: str,
    created_by: str,
) -> int:
    """Store an encrypted API key. Returns the VirtualKey ID."""
    session = get_session()
    try:
        from datetime import datetime, timezone
        vk = VirtualKey(
            provider=provider,
            key_name=key_name,
            encrypted_key=encrypt_key(api_key),
            is_active=True,
            created_by=created_by,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        session.add(vk)
        session.commit()
        session.refresh(vk)
        return vk.id
    finally:
        session.close()


def get_active_key(provider: str) -> Optional[str]:
    """Retrieve the active (decrypted) API key for a provider."""
    session = get_session()
    try:
        vk = session.exec(
            select(VirtualKey).where(
                VirtualKey.provider == provider,
                VirtualKey.is_active == True,
            )
        ).first()
        if vk:
            return decrypt_key(vk.encrypted_key)
        return None
    finally:
        session.close()


def list_virtual_keys(provider: Optional[str] = None) -> List[dict]:
    """List all virtual keys (without exposing the actual key)."""
    session = get_session()
    try:
        query = select(VirtualKey)
        if provider:
            query = query.where(VirtualKey.provider == provider)
        keys = session.exec(query).all()
        return [
            {
                "id": k.id,
                "provider": k.provider,
                "key_name": k.key_name,
                "is_active": k.is_active,
                "created_by": k.created_by,
                "created_at": k.created_at,
                # Never expose the actual key
                "key_preview": decrypt_key(k.encrypted_key)[:8] + "…" if k.encrypted_key else None,
            }
            for k in keys
        ]
    finally:
        session.close()


def revoke_virtual_key(key_id: int) -> bool:
    """Deactivate a virtual key."""
    session = get_session()
    try:
        vk = session.get(VirtualKey, key_id)
        if not vk:
            return False
        vk.is_active = False
        session.add(vk)
        session.commit()
        return True
    finally:
        session.close()


def rotate_virtual_key(key_id: int, new_api_key: str) -> bool:
    """Replace the API key for an existing virtual key entry."""
    session = get_session()
    try:
        vk = session.get(VirtualKey, key_id)
        if not vk:
            return False
        vk.encrypted_key = encrypt_key(new_api_key)
        from datetime import datetime, timezone
        vk.created_at = datetime.now(timezone.utc).isoformat()  # track rotation time
        session.add(vk)
        session.commit()
        return True
    finally:
        session.close()
