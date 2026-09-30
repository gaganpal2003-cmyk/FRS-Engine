import base64
import logging
import os
import cv2
import numpy as np
import face_recognition
from typing import List, Tuple, Optional
from api.config import (
    PROTOTEXT_PATH,
    CAFFE_MODEL_PATH,
    CONFIDENCE_THRESHOLD,
    DNN_INPUT_SIZE
)

logger = logging.getLogger("frs_api.engine")


class HeadlessFaceEngine:
    """
    Decoupled Headless Face Detection and Recognition Engine.
    Zero PyQt dependencies, thread-safe inference, CPU/CUDA acceleration.
    """
    def __init__(self):
        self.net = None
        self.cuda_available = False
        self._load_detector_model()

    def _load_detector_model(self):
        """Loads the Caffe ResNet face detector model with GPU fallback to CPU."""
        if not os.path.exists(PROTOTEXT_PATH) or not os.path.exists(CAFFE_MODEL_PATH):
            logger.warning(
                f"Caffe model files not found at {PROTOTEXT_PATH} / {CAFFE_MODEL_PATH}. "
                "Will use dlib HOG detector fallback."
            )
            return

        try:
            self.net = cv2.dnn.readNetFromCaffe(PROTOTEXT_PATH, CAFFE_MODEL_PATH)
            # Try CUDA acceleration
            try:
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                # Test forward pass with dummy image
                dummy = np.zeros((300, 300, 3), dtype=np.uint8)
                blob = cv2.dnn.blobFromImage(dummy, 1.0, (300, 300), (104.0, 177.0, 123.0))
                self.net.setInput(blob)
                self.net.forward()
                self.cuda_available = True
                logger.info("[INFO] Face Detector running on NVIDIA CUDA GPU.")
            except Exception:
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                self.cuda_available = False
                logger.info("[INFO] Face Detector running on CPU.")
        except Exception as e:
            logger.error(f"Failed to load Caffe model: {e}. Will use dlib HOG fallback.")
            self.net = None

    def decode_image_bytes(self, image_bytes: bytes) -> np.ndarray:
        """Decodes raw image bytes (JPEG, PNG, WebP) to OpenCV BGR numpy array."""
        if not image_bytes:
            raise ValueError("Image data is empty")
        
        arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise ValueError("Could not decode image bytes. Unsupported or corrupted image format.")
        return frame

    def decode_base64_image(self, base64_str: str) -> np.ndarray:
        """Decodes a base64-encoded image string to OpenCV BGR array."""
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]
        image_bytes = base64.b64decode(base64_str)
        return self.decode_image_bytes(image_bytes)

    def detect_faces(
        self,
        frame_bgr: np.ndarray,
        confidence_threshold: float = CONFIDENCE_THRESHOLD
    ) -> List[Tuple[int, int, int, int]]:
        """
        Detects faces in image and returns list of (top, right, bottom, left) coordinates.
        Primary: Caffe ResNet SSD detector.
        Fallback: dlib HOG detector if 0 faces found.
        """
        h, w = frame_bgr.shape[:2]
        face_locations = []

        if self.net is not None:
            # Resize image for SSD detector
            blob = cv2.dnn.blobFromImage(
                cv2.resize(frame_bgr, (DNN_INPUT_SIZE, DNN_INPUT_SIZE)),
                1.0,
                (DNN_INPUT_SIZE, DNN_INPUT_SIZE),
                (104.0, 177.0, 123.0)
            )
            self.net.setInput(blob)
            detections = self.net.forward()

            for i in range(detections.shape[2]):
                confidence = float(detections[0, 0, i, 2])
                if confidence >= confidence_threshold:
                    box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                    x1, y1, x2, y2 = box.astype(int)

                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)

                    # Filter out tiny artifacts
                    if (x2 - x1) >= 25 and (y2 - y1) >= 25:
                        top, right, bottom, left = y1, x2, y2, x1
                        face_locations.append((top, right, bottom, left))

        # Fallback to dlib HOG if Caffe found nothing or was not loaded
        if len(face_locations) == 0:
            rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame, number_of_times_to_upsample=1, model="hog")

        return face_locations

    def compute_encodings(
        self,
        frame_bgr: np.ndarray,
        face_locations: List[Tuple[int, int, int, int]]
    ) -> List[np.ndarray]:
        """
        Extracts 128-dimensional facial embeddings for each face location.
        """
        if not face_locations:
            return []

        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(
            rgb_frame,
            known_face_locations=face_locations,
            num_jitters=1,
            model="large"
        )
        return encodings

    def extract_single_face_encoding(
        self,
        frame_bgr: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[Tuple[int, int, int, int]], str]:
        """
        Extracts face encoding for a single face image (ideal for enrollment & 1:1 verify).
        Returns: (encoding, face_location, message)
        """
        locations = self.detect_faces(frame_bgr)
        if len(locations) == 0:
            return None, None, "No face detected in the image"
        if len(locations) > 1:
            # Sort by area descending, pick largest face
            locations.sort(key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]), reverse=True)
            logger.info("Multiple faces detected in enrollment image; selected the most prominent face.")

        target_box = locations[0]
        encodings = self.compute_encodings(frame_bgr, [target_box])
        if len(encodings) == 0:
            return None, None, "Failed to compute face embedding"

        return encodings[0], target_box, "Success"

    @staticmethod
    def distance_to_confidence(distance: float) -> float:
        """
        Maps Euclidean distance to intuitive confidence score percentage (0-100%).
        Standard dlib distance threshold: 0.40 -> ~90% match.
        """
        if distance > 1.0:
            return 0.0
        # Linear or smooth percentage mapping
        confidence = (1.0 - distance) * 100.0
        return max(0.0, min(100.0, round(confidence, 2)))


# Singleton engine instance
engine = HeadlessFaceEngine()
