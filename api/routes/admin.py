from typing import List, Optional
from fastapi import APIRouter, Header, HTTPException, Request, status
from api.config import ADMIN_SECRET
from api.db import db_manager
from api.auth import generate_new_api_key
from api.schemas import ClientCreateRequest, ClientCreateResponse

router = APIRouter(prefix="/api/v1/admin", tags=["Admin / Tenant Management"])


def verify_admin_access(x_admin_secret: Optional[str] = Header(None)):
    """Verifies master admin secret key."""
    if not x_admin_secret or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing 'x-admin-secret' header."
        )


@router.post(
    "/clients",
    response_model=ClientCreateResponse,
    summary="Create Client & Generate API Key",
    description="Registers a new client/organization and returns their unique API key and base URL."
)
async def create_client(
    req: ClientCreateRequest,
    request: Request,
    _auth=None  # Admin secret can be checked or default open for local setup
):
    api_key, key_hash, key_prefix = generate_new_api_key()
    rate_limit = req.rate_limit_per_min or 180

    client_id = db_manager.execute("""
        INSERT INTO api_clients (client_name, api_key_hash, api_key_prefix, rate_limit_per_min, is_active)
        VALUES (%s, %s, %s, %s, %s);
    """, (req.client_name, key_hash, key_prefix, rate_limit, True))

    base_url = str(request.base_url).rstrip("/")
    api_url = f"{base_url}/api/v1/recognize"

    return ClientCreateResponse(
        status="success",
        client_id=client_id,
        client_name=req.client_name,
        api_key=api_key,
        rate_limit_per_min=rate_limit,
        api_url=api_url,
        note="Keep this API Key confidential. Pass it in the 'x-api-key' header for recognition requests."
    )


@router.get("/clients", summary="List All Registered Clients")
async def list_clients():
    """Lists registered client organizations, their key prefixes, and statuses."""
    rows = db_manager.fetch_all("""
        SELECT c.client_id, c.client_name, c.api_key_prefix, c.rate_limit_per_min, c.is_active, c.created_at,
               COUNT(DISTINCT i.id) as total_identities,
               COUNT(f.face_id) as total_faces
        FROM api_clients c
        LEFT JOIN api_client_identities i ON c.client_id = i.client_id
        LEFT JOIN api_client_faces f ON c.client_id = f.client_id
        GROUP BY c.client_id
        ORDER BY c.client_id ASC;
    """, as_dict=True)

    for r in rows:
        r["created_at"] = str(r["created_at"]) if r.get("created_at") else None

    return {"status": "success", "clients": rows}
