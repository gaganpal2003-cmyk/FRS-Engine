import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import API_TITLE, API_VERSION
from api.db import db_manager
from api.service.engine import engine
from api.service.vector_index import vector_gallery
from api.schemas import HealthResponse

# Import route modules
from api.routes.recognize import router as recognize_router
from api.routes.verify import router as verify_router
from api.routes.enroll import router as enroll_router
from api.routes.identities import router as identities_router
from api.routes.admin import router as admin_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("frs_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup & shutdown."""
    logger.info("Initializing Cairo Face Recognition Engine...")
    
    # 1. Initialize database tables and sync default tenant
    try:
        db_manager.initialize_database()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # 2. Warm up vector gallery index for all clients
    try:
        vector_gallery.load_all_clients()
    except Exception as e:
        logger.error(f"Failed to warm up vector gallery: {e}")

    stats = vector_gallery.get_stats()
    logger.info(
        f"Engine Ready! Loaded {stats['total_enrolled_faces']} faces across "
        f"{stats['active_clients_cached']} client accounts."
    )

    yield

    logger.info("Shutting down Face Recognition Engine...")


# Create FastAPI application
app = FastAPI(
    title=API_TITLE,
    description="""
## High-Performance Multi-Tenant Face Recognition REST API Engine

Provides secure, low-latency face detection, 1:N recognition, 1:1 verification, and face enrollment.

### Authentication
Authenticate requests by passing your unique API key in the `x-api-key` header:
```http
x-api-key: frs_live_xxxxxxxxxxxxxxxxxxxxxxxxxx
```
    """,
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for web applications and client integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(recognize_router)
app.include_router(verify_router)
app.include_router(enroll_router)
app.include_router(identities_router)
app.include_router(admin_router)


@app.get("/", tags=["General"])
async def root():
    """Welcome and quick-start index."""
    stats = vector_gallery.get_stats()
    return {
        "service": API_TITLE,
        "version": API_VERSION,
        "status": "online",
        "documentation": "/docs",
        "endpoints": {
            "recognize": "POST /api/v1/recognize",
            "verify": "POST /api/v1/verify",
            "enroll": "POST /api/v1/enroll",
            "identities": "GET /api/v1/identities",
            "health": "GET /api/v1/health"
        },
        "stats": stats
    }


@app.get("/api/v1/health", response_model=HealthResponse, tags=["General"])
async def health_check():
    """Returns engine health status, GPU availability, and cache statistics."""
    stats = vector_gallery.get_stats()
    return HealthResponse(
        status="healthy",
        service=API_TITLE,
        version=API_VERSION,
        cuda_available=engine.cuda_available,
        active_clients_cached=stats["active_clients_cached"],
        total_enrolled_faces=stats["total_enrolled_faces"]
    )
