import argparse
import sys
from api.db import db_manager
from api.auth import generate_new_api_key
from api.config import API_PORT

def main():
    parser = argparse.ArgumentParser(description="Generate a new Client API Key for Cairo FRS Engine.")
    parser.add_argument("--name", type=str, required=False, help="Client or organization name")
    parser.add_argument("--rate-limit", type=int, default=180, help="Allowed requests per minute (default: 180)")
    parser.add_argument("--server-url", type=str, default=f"http://localhost:{API_PORT}", help="Public URL of the API server")
    parser.add_argument("--update-env", action="store_true", help="Automatically write this new API Key and URL into local .env file")

    args = parser.parse_args()

    client_name = args.name
    if not client_name:
        if sys.stdin.isatty():
            client_name = input("Enter Client / Organization Name: ").strip()
        else:
            client_name = "New Client Organization"

    if not client_name:
        print("[ERROR] Client name cannot be empty.")
        sys.exit(1)

    # Initialize DB if needed
    db_manager.initialize_database()

    # Generate key
    api_key, key_hash, key_prefix = generate_new_api_key()

    client_id = db_manager.execute("""
        INSERT INTO api_clients (client_name, api_key_hash, api_key_prefix, rate_limit_per_min, is_active)
        VALUES (%s, %s, %s, %s, %s);
    """, (client_name, key_hash, key_prefix, args.rate_limit, True))

    base_url = args.server_url.rstrip("/")
    recognize_url = f"{base_url}/api/v1/recognize"
    docs_url = f"{base_url}/docs"

    if args.update_env:
        from pathlib import Path
        env_file = Path(__file__).resolve().parent / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                if line.startswith("FRS_API_KEY="):
                    new_lines.append(f"FRS_API_KEY={api_key}\n")
                elif line.startswith("FRS_API_RECOGNIZE_URL="):
                    new_lines.append(f"FRS_API_RECOGNIZE_URL={recognize_url}\n")
                elif line.startswith("FRS_API_BASE_URL="):
                    new_lines.append(f"FRS_API_BASE_URL={base_url}/api/v1\n")
                else:
                    new_lines.append(line)
            with open(env_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print(f"[INFO] Updated {env_file.name} with new API key.")

    print("\n" + "=" * 70)
    print("  SUCCESS: NEW CLIENT API KEY CREATED")
    print("=" * 70)
    print(f" Client ID     : {client_id}")
    print(f" Client Name   : {client_name}")
    print(f" Rate Limit    : {args.rate_limit} requests / minute")
    print(f" API Key       : {api_key}")
    print(f" API Base URL  : {base_url}/api/v1")
    print(f" Recognize URL : {recognize_url}")
    print(f" Swagger Docs  : {docs_url}")
    print("-" * 70)
    print("  WHAT TO SEND TO THE CLIENT:")
    print("-" * 70)
    print(f" 1. API URL   : {recognize_url}")
    print(f" 2. API Key   : {api_key}")
    print(f" 3. Header    : x-api-key: {api_key}")
    print(f" 4. Swagger   : {docs_url}")
    print("-" * 70)
    print("  PYTHON CODE FOR CLIENT:")
    print("-" * 70)
    print(f'''import requests

url = "{recognize_url}"
headers = {{"x-api-key": "{api_key}"}}
files = {{"file": open("person_photo.jpg", "rb")}}

response = requests.post(url, headers=headers, files=files)
print(response.json())
''')
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
