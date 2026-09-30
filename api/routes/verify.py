from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
import face_recognition
import numpy as np
from api.auth import get_current_client
from api.config import DEFAULT_TOLERANCE
from api.db import db_manager
from api.schemas import VerifyResponse
from api.service.engine import engine

router = APIRouter(prefix="/api/v1", tags=["Verification"])


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="1:1 Face Verification",
    description="Compares two face images (or one face image against an enrolled person_id) to verify if they match."
)
async def verify_faces(
    file1: Optional[UploadFile] = File(None, description="Primary face image to verify"),
    file2: Optional[UploadFile] = File(None, description="Secondary face image to compare against (Option A)"),
    person_id: Optional[str] = Form(None, description="Enrolled person identifier to compare against (Option B)"),
    tolerance: Optional[float] = Form(DEFAULT_TOLERANCE, description="Verification threshold (default 0.40)"),
    client: dict = Depends(get_current_client)
):
    if not file1:
        raise HTTPException(status_code=400, detail="Primary face image 'file1' is required.")

    # Decode and extract encoding from file1
    try:
        bytes1 = await file1.read()
        frame1 = engine.decode_image_bytes(bytes1)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file1: {e}")

    enc1, _, msg1 = engine.extract_single_face_encoding(frame1)
    if enc1 is None:
        raise HTTPException(status_code=400, detail=f"Image 1 error: {msg1}")

    enc2 = None
    target_name = "Target"

    if file2:
        # Option A: 1:1 image comparison
        try:
            bytes2 = await file2.read()
            frame2 = engine.decode_image_bytes(bytes2)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error reading file2: {e}")

        enc2, _, msg2 = engine.extract_single_face_encoding(frame2)
        if enc2 is None:
            raise HTTPException(status_code=400, detail=f"Image 2 error: {msg2}")
        target_name = "Image 2"

    elif person_id:
        # Option B: Verify against registered person_id
        client_id = client["client_id"]
        row = db_manager.fetch_one("""
            SELECT f.face_encoding, i.name 
            FROM api_client_faces f
            INNER JOIN api_client_identities i ON f.identity_id = i.id
            WHERE f.client_id = %s AND i.person_identifier = %s
            LIMIT 1;
        """, (client_id, person_id), as_dict=True)

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Person '{person_id}' not found in your enrolled gallery."
            )

        target_name = row["name"]
        enc_str = row["face_encoding"].replace('[', '').replace(']', '').replace(',', ' ').replace('\n', ' ')
        enc_arr = np.fromstring(enc_str, sep=' ', dtype=np.float64)
        if enc_arr.size < 128:
            raise HTTPException(status_code=500, detail="Corrupted face encoding in gallery.")
        enc2 = enc_arr[:128]

    else:
        raise HTTPException(
            status_code=400,
            detail="You must provide either 'file2' (second image) or 'person_id' (enrolled ID) to compare against."
        )

    # Calculate distance
    dist = float(face_recognition.face_distance([enc2], enc1)[0])
    threshold = tolerance if tolerance is not None else DEFAULT_TOLERANCE
    is_match = bool(dist <= threshold)
    similarity = engine.distance_to_confidence(dist)

    message = f"Faces match {target_name}!" if is_match else f"Faces do not match {target_name}."

    return VerifyResponse(
        status="success",
        is_match=is_match,
        similarity=similarity,
        distance=round(dist, 4),
        threshold=threshold,
        message=message
    )
