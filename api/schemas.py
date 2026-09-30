from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class BoundingBox(BaseModel):
    top: int = Field(..., description="Top Y coordinate")
    right: int = Field(..., description="Right X coordinate")
    bottom: int = Field(..., description="Bottom Y coordinate")
    left: int = Field(..., description="Left X coordinate")


class FaceRecognitionResult(BaseModel):
    box: BoundingBox
    matched: bool = Field(..., description="True if a known identity was matched")
    person_id: Optional[str] = Field(None, description="External unique identifier of person")
    name: str = Field(..., description="Recognized name or 'Unknown'")
    confidence: float = Field(..., description="Confidence score percentage (0-100%)")
    distance: float = Field(..., description="Euclidean distance between face encodings (lower is closer)")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom metadata fields")


class RecognizeResponse(BaseModel):
    status: str = "success"
    processing_time_ms: float
    faces_detected: int
    results: List[FaceRecognitionResult]


class VerifyResponse(BaseModel):
    status: str = "success"
    is_match: bool
    similarity: float = Field(..., description="Match similarity percentage (0-100%)")
    distance: float = Field(..., description="Vector distance")
    threshold: float = Field(..., description="Tolerance threshold used")
    message: str


class EnrollResponse(BaseModel):
    status: str = "success"
    person_id: str
    name: str
    face_id: int
    faces_total: int
    message: str


class IdentityItem(BaseModel):
    id: int
    person_identifier: str
    name: str
    faces_count: int
    metadata: Optional[Dict[str, Any]] = None
    is_blacklist: bool = False
    created_at: Optional[str] = None


class ClientCreateRequest(BaseModel):
    client_name: str = Field(..., min_length=2, max_length=120, description="Organization or customer name")
    rate_limit_per_min: Optional[int] = Field(180, ge=10, le=10000, description="Requests per minute allowance")


class ClientCreateResponse(BaseModel):
    status: str = "success"
    client_id: int
    client_name: str
    api_key: str = Field(..., description="Client API Key - Copy now as it won't be displayed again")
    rate_limit_per_min: int
    api_url: str
    note: str = "Keep this API Key confidential. Pass it in the 'x-api-key' header for requests."


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "Cairo FRS Recognition Engine"
    version: str = "1.0.0"
    cuda_available: bool
    active_clients_cached: int
    total_enrolled_faces: int
