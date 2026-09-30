# Face Recognition REST API Engine 🚀

A high-performance, multi-tenant Face Recognition REST API engine built with **FastAPI**, **OpenCV DNN (Caffe ResNet SSD)**, and **dlib facial embeddings (128-dimensional)**.

Designed for production integration with external client applications, mobile apps, web portals, biometric attendance systems, and security camera pipelines.

---

## ✨ Features

- **⚡ Fast Face Detection & Recognition**: Deep neural network face detection (Caffe ResNet SSD) with GPU (CUDA) acceleration and automatic CPU fallback.
- **🔍 1:N Face Recognition**: In-memory vector gallery index providing ultra-low latency searches across thousands of enrolled faces.
- **🛡️ 1:1 Face Verification**: Verify whether a probe face matches a specific identity.
- **👤 Face Enrollment**: Dynamic enrollment supporting multiple face embeddings per identity with automatic largest-face cropping.
- **🏢 Multi-Tenant Architecture**: Complete tenant isolation. Each tenant/client organization has its own secure API key (`x-api-key`) and isolated gallery index.
- **📊 Real-time Monitoring & Health Check**: Instant metrics on active cached tenants, total enrolled faces, and GPU inference status.
- **🐳 Docker & Cloud Ready**: Fully containerized and optimized for fast deployment on Render, AWS, GCP, or local servers.

---

## 📁 Repository Structure

```text
.
├── api/                                # Core REST API Engine Package
│   ├── routes/                         # API Route Handlers
│   │   ├── admin.py                    # Tenant administration & key creation
│   │   ├── enroll.py                   # Face enrollment endpoints
│   │   ├── identities.py               # Enrolled identity queries & deletions
│   │   ├── recognize.py                # 1:N Face recognition endpoints
│   │   └── verify.py                   # 1:1 Face verification endpoints
│   ├── service/                        # Underlying Inference & Indexing Engine
│   │   ├── engine.py                   # Headless Caffe ResNet SSD detector & face embedder
│   │   └── vector_index.py             # In-memory vector gallery with thread-safe locks
│   ├── auth.py                         # API Key validation & tenant security
│   ├── config.py                       # Configuration & environment variable resolution
│   ├── db.py                           # MySQL connection pooling & auto-migration
│   ├── main.py                         # FastAPI application initialization & lifespan
│   └── schemas.py                      # Pydantic request/response validation models
├── config/
│   └── settings.ini                    # Default fallback configuration
├── Detection/
│   └── FRS_MODEL/                      # Pre-trained Face Detector weights
│       ├── deploy_prototext.txt        # ResNet SSD Caffe architecture
│       └── face_caffe_model            # Pre-trained Caffe model weights
├── .dockerignore                       # Excludes non-API files & secrets from Docker builds
├── .env.example                        # Template environment variables
├── .gitignore                          # Excludes unused legacy files, secrets & logs
├── create_client_key.py                # CLI tool to provision new tenant API keys
├── Dockerfile                          # Optimized Python 3.10-slim container definition
├── requirements.txt                    # Python dependencies
├── run_api.py                          # API Server launch script (Uvicorn)
├── test_client_api.py                  # Integration test suite for API endpoints
├── test_sample_face.jpg                # Sample probe image for quick endpoint tests
├── CLIENT_INTEGRATION_AND_DATABASE_GUIDE.md # Client integration guide & API specs
└── RENDER_FRS_DEPLOYMENT_GUIDE.md      # Step-by-step cloud deployment guide
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- MySQL Server (5.7 or 8.0+)
- CMake & C++ Build Tools (required for building `dlib`)

### 2. Installation

1. **Clone the repository:**
   ```bash
   git clone <YOUR_GITHUB_REPO_URL>
   cd FRS_Gagan_Sept2026-main
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure Environment:**
   Copy `.env.example` to `.env` and fill in your MySQL credentials:
   ```bash
   # Windows
   copy .env.example .env

   # Linux / macOS
   cp .env.example .env
   ```

---

## ⚙️ Running the API Server

Start the API server locally:
```bash
python run_api.py
```

The server starts on `http://localhost:8000`:
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check Endpoint**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

## 🔑 Generating a Client API Key

Each tenant requires a unique API key. Use the built-in generator script:

```bash
python create_client_key.py --name "Acme Corp" --rate-limit 300 --update-env
```

This will:
1. Register the tenant in the database.
2. Generate an active API key (`frs_live_...`).
3. Output ready-to-use Python client code.
4. Optionally update `.env` for immediate local testing.

---

## 🧪 Testing the API Engine

Run the automated integration test script:
```bash
python test_client_api.py
```

It validates:
1. Server health & GPU availability (`GET /api/v1/health`).
2. Tenant authentication & identity listing (`GET /api/v1/identities`).
3. 1:N Face recognition against the probe photo (`POST /api/v1/recognize`).

---

## 📡 API Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/health` | Service health, CUDA status, and cache stats | No |
| `POST` | `/api/v1/recognize` | 1:N Face Recognition (Multipart file or Base64) | `x-api-key` |
| `POST` | `/api/v1/verify` | 1:1 Face Verification against a person ID | `x-api-key` |
| `POST` | `/api/v1/enroll` | Enroll a new identity or append faces | `x-api-key` |
| `GET` | `/api/v1/identities` | List all enrolled identities for tenant | `x-api-key` |
| `DELETE` | `/api/v1/identities/{person_identifier}` | Delete an identity & cached faces | `x-api-key` |
| `POST` | `/api/v1/admin/clients` | Provision new client tenant | `Admin-Secret` |

---

## 🐳 Docker Deployment

Build and run using Docker:

```bash
# Build the container
docker build -t frs-api-engine .

# Run the container
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name frs-engine \
  frs-api-engine
```

For complete cloud deployment instructions (e.g. Render, AWS, Linux VPS), refer to [RENDER_FRS_DEPLOYMENT_GUIDE.md](RENDER_FRS_DEPLOYMENT_GUIDE.md).

---

## 🔒 Security Best Practices

- **Never commit `.env` or `.default_api_key.txt`**: These files are included in `.gitignore` by default.
- Always use environment variables for database credentials and admin secrets in production.
- Use HTTPS in production to ensure API keys and facial biometric data are encrypted in transit.

---

## 📄 License
Internal Proprietary & Confidential.
