import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from api.auth import get_current_client
from api.db import db_manager
from api.schemas import IdentityItem
from api.service.vector_index import vector_gallery

router = APIRouter(prefix="/api/v1/identities", tags=["Identities"])


@router.get("", response_model=List[IdentityItem], summary="List Enrolled Identities")
async def list_identities(client: dict = Depends(get_current_client)):
    """Returns a list of all identities enrolled under your client account."""
    client_id = client["client_id"]
    rows = db_manager.fetch_all("""
        SELECT i.id, i.person_identifier, i.name, i.metadata, i.is_blacklist, i.created_at,
               COUNT(f.face_id) as faces_count
        FROM api_client_identities i
        LEFT JOIN api_client_faces f ON i.id = f.identity_id
        WHERE i.client_id = %s
        GROUP BY i.id
        ORDER BY i.id DESC;
    """, (client_id,), as_dict=True)

    results = []
    for r in rows:
        meta = {}
        if r.get("metadata"):
            try:
                meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"]
            except Exception:
                pass

        results.append(IdentityItem(
            id=r["id"],
            person_identifier=r["person_identifier"],
            name=r["name"],
            faces_count=r["faces_count"] or 0,
            metadata=meta,
            is_blacklist=bool(r["is_blacklist"]),
            created_at=str(r["created_at"]) if r.get("created_at") else None
        ))

    return results


@router.get("/{person_identifier}", response_model=IdentityItem, summary="Get Identity Details")
async def get_identity(person_identifier: str, client: dict = Depends(get_current_client)):
    """Fetches details for a single enrolled person."""
    client_id = client["client_id"]
    r = db_manager.fetch_one("""
        SELECT i.id, i.person_identifier, i.name, i.metadata, i.is_blacklist, i.created_at,
               COUNT(f.face_id) as faces_count
        FROM api_client_identities i
        LEFT JOIN api_client_faces f ON i.id = f.identity_id
        WHERE i.client_id = %s AND i.person_identifier = %s
        GROUP BY i.id;
    """, (client_id, person_identifier), as_dict=True)

    if not r:
        raise HTTPException(status_code=404, detail=f"Identity '{person_identifier}' not found.")

    meta = {}
    if r.get("metadata"):
        try:
            meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"]
        except Exception:
            pass

    return IdentityItem(
        id=r["id"],
        person_identifier=r["person_identifier"],
        name=r["name"],
        faces_count=r["faces_count"] or 0,
        metadata=meta,
        is_blacklist=bool(r["is_blacklist"]),
        created_at=str(r["created_at"]) if r.get("created_at") else None
    )


@router.delete("/{person_identifier}", summary="Delete Enrolled Identity")
async def delete_identity(person_identifier: str, client: dict = Depends(get_current_client)):
    """Deletes an enrolled identity and all associated face embeddings."""
    client_id = client["client_id"]
    row = db_manager.fetch_one(
        "SELECT id FROM api_client_identities WHERE client_id = %s AND person_identifier = %s;",
        (client_id, person_identifier)
    )

    if not row:
        raise HTTPException(status_code=404, detail=f"Identity '{person_identifier}' not found.")

    # Delete from DB (CASCADE deletes faces)
    db_manager.execute(
        "DELETE FROM api_client_identities WHERE client_id = %s AND person_identifier = %s;",
        (client_id, person_identifier)
    )

    # Remove from memory index
    vector_gallery.remove_identity(client_id, person_identifier)

    return {
        "status": "success",
        "message": f"Successfully deleted identity '{person_identifier}'."
    }
