import hashlib
import secrets
import time
from collections import defaultdict
from typing import Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from api.config import ADMIN_SECRET
from api.db import db_manager

# API Key Header definition for Swagger UI
api_key_header_scheme = APIKeyHeader(name="x-api-key", auto_error=False)

# In-memory client cache: key_hash -> client_dict, cached for 60s
_client_cache = {}
_client_cache_expiry = {}

# Simple sliding window rate limiter: client_id -> list of timestamps
_rate_limit_tracker = defaultdict(list)


def generate_new_api_key():
    """Generates a secure API key and its hash."""
    raw_token = secrets.token_hex(20)
    api_key = f"frs_live_{raw_token}"
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    key_prefix = api_key[:12]
    return api_key, key_hash, key_prefix


def check_rate_limit(client_id: int, limit_per_minute: int) -> bool:
    """Sliding-window rate limiter per client."""
    now = time.time()
    one_minute_ago = now - 60
    
    # Prune timestamps older than 60s
    timestamps = [ts for ts in _rate_limit_tracker[client_id] if ts > one_minute_ago]
    if len(timestamps) >= limit_per_minute:
        _rate_limit_tracker[client_id] = timestamps
        return False
    
    timestamps.append(now)
    _rate_limit_tracker[client_id] = timestamps
    return True


def invalidate_client_cache(key_hash: Optional[str] = None):
    global _client_cache, _client_cache_expiry
    if key_hash and key_hash in _client_cache:
        del _client_cache[key_hash]
        del _client_cache_expiry[key_hash]
    else:
        _client_cache.clear()
        _client_cache_expiry.clear()


async def get_current_client(
    x_api_key: Optional[str] = Security(api_key_header_scheme),
    authorization: Optional[str] = Header(None)
) -> dict:
    """
    Validates API key from 'x-api-key' header or 'Authorization: Bearer <key>'.
    Returns client info dict: {client_id, client_name, rate_limit_per_min}.
    """
    raw_key = None
    if x_api_key:
        raw_key = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        raw_key = authorization[7:].strip()

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key missing. Please provide 'x-api-key' header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # Master admin secret bypass (allows master key to be used as API key)
    if raw_key == ADMIN_SECRET:
        return {
            "client_id": 1,
            "client_name": "Master Administrator",
            "rate_limit_per_min": 100000
        }

    # Hash the incoming key
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    # Check memory cache
    now = time.time()
    if key_hash in _client_cache and now < _client_cache_expiry.get(key_hash, 0):
        client = _client_cache[key_hash]
    else:
        # Query MySQL database
        row = db_manager.fetch_one("""
            SELECT client_id, client_name, rate_limit_per_min, is_active 
            FROM api_clients 
            WHERE api_key_hash = %s;
        """, (key_hash,), as_dict=True)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key."
            )

        if not row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API Key is inactive or revoked."
            )

        client = {
            "client_id": row["client_id"],
            "client_name": row["client_name"],
            "rate_limit_per_min": row["rate_limit_per_min"] or 180
        }
        _client_cache[key_hash] = client
        _client_cache_expiry[key_hash] = now + 60  # Cache for 60 seconds

    # Check rate limit
    if not check_rate_limit(client["client_id"], client["rate_limit_per_min"]):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit of {client['rate_limit_per_min']} requests/minute exceeded."
        )

    return client
