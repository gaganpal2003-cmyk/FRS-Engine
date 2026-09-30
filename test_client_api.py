import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DOTENV_PATH = BASE_DIR / ".env"
if DOTENV_PATH.exists():
    load_dotenv(DOTENV_PATH)

BASE_URL = os.getenv("FRS_API_BASE_URL", "http://localhost:8000/api/v1").replace("/api/v1", "")
SERVER_HEALTH_URL = f"{BASE_URL}/api/v1/health"
SERVER_RECOGNIZE_URL = os.getenv("FRS_API_RECOGNIZE_URL", f"{BASE_URL}/api/v1/recognize")
SERVER_IDENTITIES_URL = f"{BASE_URL}/api/v1/identities"

KEY_FILE = BASE_DIR / ".default_api_key.txt"

def load_api_key():
    # 1. Check .env first
    env_key = os.getenv("FRS_API_KEY")
    if env_key:
        return env_key.strip()
    # 2. Check .default_api_key.txt
    if KEY_FILE.exists():
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("API Key:"):
                    return line.split(":", 1)[1].strip()
    return ""

def main():
    api_key = load_api_key()
    if not api_key:
        print("[WARNING] No API key found in .default_api_key.txt. Using dummy or pass via FRS_TEST_API_KEY.")
    
    print("\n" + "=" * 65)
    print("  Testing Cairo Face Recognition API Engine")
    print("=" * 65)
    print(f" Target Server : {BASE_URL}")
    print(f" Using API Key : {api_key[:16]}... (hidden)")
    print("-" * 65)

    headers = {"x-api-key": api_key}

    # 1. Health check
    try:
        print("[1/3] Testing GET /api/v1/health...")
        res = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
        print(f"      Status: {res.status_code}")
        print(f"      Response: {res.json()}")
    except requests.exceptions.ConnectionError:
        print("[ERROR] Could not connect to API server. Is 'python run_api.py' running?")
        sys.exit(1)

    # 2. List enrolled identities
    print("\n[2/3] Testing GET /api/v1/identities...")
    res = requests.get(f"{BASE_URL}/api/v1/identities", headers=headers, timeout=5)
    print(f"      Status: {res.status_code}")
    if res.status_code == 200:
        identities = res.json()
        print(f"      Found {len(identities)} enrolled identities:")
        for idx, item in enumerate(identities[:5]):
            print(f"        - [{item['person_identifier']}] {item['name']} ({item['faces_count']} faces)")
        if len(identities) > 5:
            print(f"        ... and {len(identities) - 5} more.")
    else:
        print(f"      Error: {res.text}")

    # 3. Test Recognition with a sample image if exists
    test_img = Path(__file__).resolve().parent / "test_sample_face.jpg"
    if not test_img.exists():
        # Try to extract one sample from database for testing
        try:
            from api.db import db_manager
            row = db_manager.fetch_one("SELECT face_image FROM api_client_faces WHERE face_image IS NOT NULL LIMIT 1;")
            if row and row[0]:
                with open(test_img, "wb") as f:
                    f.write(row[0])
                print(f"Extracted sample face image from DB to {test_img.name}")
        except Exception as e:
            pass

    if test_img.exists():
        print(f"\n[3/3] Testing POST /api/v1/recognize with {test_img.name}...")
        with open(test_img, "rb") as f:
            files = {"file": (test_img.name, f, "image/jpeg")}
            res = requests.post(f"{BASE_URL}/api/v1/recognize", headers=headers, files=files, timeout=10)
            print(f"      Status: {res.status_code}")
            print(f"      Response: {res.json()}")
    else:
        print("\n[3/3] Skipped POST /api/v1/recognize (no test image found). You can run:")
        print(f"      curl -X POST \"{BASE_URL}/api/v1/recognize\" -H \"x-api-key: {api_key}\" -F \"file=@your_photo.jpg\"")

    print("\n" + "=" * 65)
    print("  Tests Completed!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
