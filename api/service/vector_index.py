import json
import logging
import threading
import numpy as np
import face_recognition
from typing import Dict, List, Optional, Tuple, Any
from api.db import db_manager
from api.config import DEFAULT_TOLERANCE
from api.service.engine import engine

logger = logging.getLogger("frs_api.vector_index")


class VectorGalleryIndex:
    """
    In-memory multi-tenant vector gallery index.
    Keeps each client's face encodings in high-speed RAM for sub-50ms 1:N matching.
    Thread-safe for dynamic face enrollment without server restarts.
    """
    def __init__(self):
        # client_id -> {"encodings": np.ndarray (N, 128), "identities": List[dict]}
        self.client_indices: Dict[int, Dict[str, Any]] = {}
        self.lock = threading.RLock()

    def load_all_clients(self):
        """Warms up vector index for all active clients from the database."""
        with self.lock:
            logger.info("Loading face galleries for all clients into memory...")
            clients = db_manager.fetch_all("SELECT client_id, client_name FROM api_clients WHERE is_active=TRUE;", as_dict=True)
            for client in clients:
                self.reload_client(client["client_id"])
            logger.info(f"Vector gallery loaded for {len(self.client_indices)} clients.")

    def reload_client(self, client_id: int):
        """Reloads/refreshes vector gallery for a single client."""
        with self.lock:
            rows = db_manager.fetch_all("""
                SELECT f.face_id, f.identity_id, f.face_encoding,
                       i.person_identifier, i.name, i.metadata, i.is_blacklist
                FROM api_client_faces f
                INNER JOIN api_client_identities i ON f.identity_id = i.id
                WHERE f.client_id = %s;
            """, (client_id,), as_dict=True)

            encodings_list = []
            identities_list = []

            for row in rows:
                encoding_str = row.get("face_encoding")
                if not encoding_str:
                    continue

                # Parse float encoding array
                enc_clean = encoding_str.replace('[', '').replace(']', '').replace(',', ' ').replace('\n', ' ')
                enc_array = np.fromstring(enc_clean, sep=' ', dtype=np.float64)

                if enc_array.size > 0 and enc_array.size % 128 == 0:
                    reshaped = enc_array.reshape(-1, 128)
                    
                    # Parse metadata JSON
                    meta = {}
                    if row.get("metadata"):
                        try:
                            meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
                        except Exception:
                            meta = {}

                    identity_data = {
                        "identity_id": row["identity_id"],
                        "person_identifier": row["person_identifier"],
                        "name": row["name"],
                        "metadata": meta,
                        "is_blacklist": bool(row["is_blacklist"])
                    }

                    for single_enc in reshaped:
                        encodings_list.append(single_enc)
                        identities_list.append(identity_data)

            if encodings_list:
                self.client_indices[client_id] = {
                    "encodings": np.array(encodings_list),
                    "identities": identities_list
                }
                logger.info(f"Client {client_id}: Indexed {len(encodings_list)} faces across {len(set(i['person_identifier'] for i in identities_list))} persons.")
            else:
                self.client_indices[client_id] = {
                    "encodings": np.empty((0, 128)),
                    "identities": []
                }
                logger.info(f"Client {client_id}: Gallery is empty.")

    def search(
        self,
        client_id: int,
        query_encoding: np.ndarray,
        tolerance: float = DEFAULT_TOLERANCE
    ) -> Tuple[Optional[Dict[str, Any]], float, float]:
        """
        Performs 1:N Euclidean distance vector search against the client's gallery.
        Returns: (matched_identity_dict or None, distance, confidence_percentage)
        """
        with self.lock:
            client_data = self.client_indices.get(client_id)
            if not client_data or len(client_data["encodings"]) == 0:
                # Gallery is empty
                return None, 1.0, 0.0

            known_encodings = client_data["encodings"]
            identities = client_data["identities"]

            # Compute Euclidean distances to all known faces
            distances = face_recognition.face_distance(known_encodings, query_encoding)
            best_idx = int(np.argmin(distances))
            min_dist = float(distances[best_idx])
            confidence = engine.distance_to_confidence(min_dist)

            if min_dist <= tolerance:
                matched_identity = identities[best_idx]
                return matched_identity, min_dist, confidence
            else:
                return None, min_dist, confidence

    def add_face(
        self,
        client_id: int,
        identity_id: int,
        person_identifier: str,
        name: str,
        encoding: np.ndarray,
        metadata: Optional[dict] = None,
        is_blacklist: bool = False
    ):
        """Dynamically appends a new face encoding into client's memory index."""
        with self.lock:
            if client_id not in self.client_indices:
                self.client_indices[client_id] = {
                    "encodings": np.empty((0, 128)),
                    "identities": []
                }

            identity_data = {
                "identity_id": identity_id,
                "person_identifier": person_identifier,
                "name": name,
                "metadata": metadata or {},
                "is_blacklist": is_blacklist
            }

            current_encs = self.client_indices[client_id]["encodings"]
            if current_encs.size == 0:
                self.client_indices[client_id]["encodings"] = np.array([encoding])
            else:
                self.client_indices[client_id]["encodings"] = np.vstack([current_encs, encoding])

            self.client_indices[client_id]["identities"].append(identity_data)
            logger.info(f"Client {client_id}: Dynamically added face for {name} ({person_identifier}). Total: {len(self.client_indices[client_id]['identities'])}")

    def remove_identity(self, client_id: int, person_identifier: str):
        """Removes all face encodings belonging to a person from client's memory index."""
        with self.lock:
            if client_id not in self.client_indices:
                return

            client_data = self.client_indices[client_id]
            identities = client_data["identities"]
            encodings = client_data["encodings"]

            keep_indices = [
                i for i, item in enumerate(identities)
                if item["person_identifier"] != person_identifier
            ]

            if len(keep_indices) == len(identities):
                return

            if keep_indices:
                self.client_indices[client_id]["encodings"] = encodings[keep_indices]
                self.client_indices[client_id]["identities"] = [identities[i] for i in keep_indices]
            else:
                self.client_indices[client_id]["encodings"] = np.empty((0, 128))
                self.client_indices[client_id]["identities"] = []

            logger.info(f"Client {client_id}: Removed {person_identifier} from memory index.")

    def get_stats(self) -> Dict[str, Any]:
        """Returns index status and total cached faces."""
        with self.lock:
            total_faces = sum(len(d["identities"]) for d in self.client_indices.values())
            return {
                "active_clients_cached": len(self.client_indices),
                "total_enrolled_faces": total_faces
            }


# Singleton gallery instance
vector_gallery = VectorGalleryIndex()
