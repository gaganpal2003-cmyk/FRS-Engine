import time
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Request, Body
from pydantic import BaseModel
from api.auth import get_current_client
from api.config import DEFAULT_TOLERANCE
from api.db import db_manager
from api.schemas import RecognizeResponse, FaceRecognitionResult, BoundingBox
from api.service.engine import engine
from api.service.vector_index import vector_gallery

router = APIRouter(prefix="/api/v1", tags=["Recognition"])


class RecognizeJsonBody(BaseModel):
    image_base64: str
    tolerance: Optional[float] = DEFAULT_TOLERANCE


async def _process_recognition(
    frame_bgr,
    client_id: int,
    tolerance_val: float,
    request: Request,
    start_time: float
) -> RecognizeResponse:
    # 2. Detect Faces
    face_boxes = engine.detect_faces(frame_bgr)
    results = []

    # 3. Compute Encodings & Search in Gallery
    if face_boxes:
        encodings = engine.compute_encodings(frame_bgr, face_boxes)

        for box, enc in zip(face_boxes, encodings):
            top, right, bottom, left = box
            bbox = BoundingBox(top=int(top), right=int(right), bottom=int(bottom), left=int(left))

            matched_identity, dist, confidence = vector_gallery.search(
                client_id=client_id,
                query_encoding=enc,
                tolerance=tolerance_val
            )

            if matched_identity:
                result_item = FaceRecognitionResult(
                    box=bbox,
                    matched=True,
                    person_id=matched_identity["person_identifier"],
                    name=matched_identity["name"],
                    confidence=confidence,
                    distance=round(dist, 4),
                    metadata=matched_identity.get("metadata", {})
                )
                try:
                    client_ip = request.client.host if request.client else "unknown"
                    db_manager.execute("""
                        INSERT INTO api_recognition_logs (client_id, matched_identity_id, confidence_score, processing_time_ms, request_ip)
                        VALUES (%s, %s, %s, %s, %s);
                    """, (client_id, matched_identity["identity_id"], confidence, 0.0, client_ip))
                except Exception:
                    pass
            else:
                result_item = FaceRecognitionResult(
                    box=bbox,
                    matched=False,
                    person_id=None,
                    name="Unknown",
                    confidence=confidence,
                    distance=round(dist, 4),
                    metadata={}
                )

            results.append(result_item)

    total_time_ms = round((time.time() - start_time) * 1000, 2)

    return RecognizeResponse(
        status="success",
        processing_time_ms=total_time_ms,
        faces_detected=len(results),
        results=results
    )


@router.post(
    "/recognize",
    response_model=RecognizeResponse,
    summary="1:N Face Recognition (File Upload)",
    description="Detects and recognizes faces in an uploaded image file (or base64 form field) against your client gallery."
)
async def recognize_faces(
    request: Request,
    file: Optional[UploadFile] = File(None, description="Image file (JPG/PNG/WebP)"),
    image_base64: Optional[str] = Form(None, description="Optional Base64 encoded image string"),
    tolerance: Optional[float] = Form(DEFAULT_TOLERANCE, description="Recognition distance tolerance (default 0.40)"),
    client: dict = Depends(get_current_client)
):
    start_time = time.time()
    frame_bgr = None

    # Support JSON fallback if sent to this endpoint with application/json
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            json_body = await request.json()
            if "image_base64" in json_body:
                frame_bgr = engine.decode_base64_image(json_body["image_base64"])
            if "tolerance" in json_body and json_body["tolerance"] is not None:
                tolerance = float(json_body["tolerance"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"JSON parsing error: {e}")

    # Standard multipart/form-data upload
    if frame_bgr is None:
        try:
            if file is not None and file.filename:
                contents = await file.read()
                frame_bgr = engine.decode_image_bytes(contents)
            elif image_base64:
                frame_bgr = engine.decode_base64_image(image_base64)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No image provided. Please select an image file to upload."
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Image decoding error: {str(e)}")

    tolerance_val = tolerance if tolerance is not None else DEFAULT_TOLERANCE
    return await _process_recognition(frame_bgr, client["client_id"], tolerance_val, request, start_time)


@router.post(
    "/recognize-base64",
    response_model=RecognizeResponse,
    summary="1:N Face Recognition (JSON Base64)",
    description="Detects and recognizes faces using a JSON payload with a base64 encoded image string."
)
async def recognize_faces_base64(
    request: Request,
    payload: RecognizeJsonBody,
    client: dict = Depends(get_current_client)
):
    start_time = time.time()
    try:
        frame_bgr = engine.decode_base64_image(payload.image_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 image decoding error: {str(e)}")

    tolerance_val = payload.tolerance if payload.tolerance is not None else DEFAULT_TOLERANCE
    return await _process_recognition(frame_bgr, client["client_id"], tolerance_val, request, start_time)
