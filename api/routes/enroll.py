import json
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from api.auth import get_current_client
from api.db import db_manager
from api.schemas import EnrollResponse
from api.service.engine import engine
from api.service.vector_index import vector_gallery

router = APIRouter(prefix="/api/v1", tags=["Enrollment"])


@router.post(
    "/enroll",
    response_model=EnrollResponse,
    summary="Enroll / Register Face",
    description="Registers a new person or adds an additional face photo to an existing person's gallery."
)
async def enroll_face(
    person_id: str = Form(..., description="Unique person identifier (e.g. employee ID or user ID)"),
    name: str = Form(..., description="Full name of person"),
    file: UploadFile = File(..., description="Face photograph for enrollment"),
    metadata: Optional[str] = Form("{}", description="Optional JSON string of custom metadata attributes"),
    is_blacklist: Optional[bool] = Form(False, description="Flag if this person is blacklisted/watchlisted"),
    client: dict = Depends(get_current_client)
):
    client_id = client["client_id"]

    # 1. Decode Image & Compute 128-d Embedding
    try:
        contents = await file.read()
        frame_bgr = engine.decode_image_bytes(contents)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image reading error: {str(e)}")

    encoding, bbox, msg = engine.extract_single_face_encoding(frame_bgr)
    if encoding is None:
        raise HTTPException(status_code=400, detail=f"Face enrollment failed: {msg}")

    # Parse metadata JSON
    meta_dict = {}
    if metadata:
        try:
            meta_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
        except Exception:
            meta_dict = {"raw_meta": metadata}

    # 2. Check or create identity in database
    identity = db_manager.fetch_one("""
        SELECT id, name, metadata, is_blacklist 
        FROM api_client_identities 
        WHERE client_id = %s AND person_identifier = %s;
    """, (client_id, person_id), as_dict=True)

    if identity:
        identity_id = identity["id"]
        # Update name or metadata if changed
        db_manager.execute("""
            UPDATE api_client_identities 
            SET name = %s, metadata = %s, is_blacklist = %s 
            WHERE id = %s;
        """, (name, json.dumps(meta_dict), bool(is_blacklist), identity_id))
    else:
        identity_id = db_manager.execute("""
            INSERT INTO api_client_identities 
            (client_id, person_identifier, name, metadata, is_blacklist) 
            VALUES (%s, %s, %s, %s, %s);
        """, (client_id, person_id, name, json.dumps(meta_dict), bool(is_blacklist)))

    # 3. Store face encoding string in database
    encoding_str = json.dumps(encoding.tolist())
    face_id = db_manager.execute("""
        INSERT INTO api_client_faces 
        (client_id, identity_id, face_encoding, face_image) 
        VALUES (%s, %s, %s, %s);
    """, (client_id, identity_id, encoding_str, contents))

    # 4. Count total faces for this identity
    total_faces_row = db_manager.fetch_one(
        "SELECT COUNT(*) FROM api_client_faces WHERE identity_id = %s;",
        (identity_id,)
    )
    total_faces = total_faces_row[0] if total_faces_row else 1

    # 5. Immediately update in-memory gallery index
    vector_gallery.add_face(
        client_id=client_id,
        identity_id=identity_id,
        person_identifier=person_id,
        name=name,
        encoding=encoding,
        metadata=meta_dict,
        is_blacklist=bool(is_blacklist)
    )

    return EnrollResponse(
        status="success",
        person_id=person_id,
        name=name,
        face_id=face_id,
        faces_total=total_faces,
        message=f"Successfully enrolled face for {name} ({person_id})."
    )
