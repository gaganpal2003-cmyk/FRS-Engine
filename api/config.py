import os
import configparser
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DOTENV_PATH = BASE_DIR / ".env"
if DOTENV_PATH.exists():
    load_dotenv(DOTENV_PATH)

CONFIG_INI_PATH = BASE_DIR / "config" / "settings.ini"

# Read settings.ini
config_parser = configparser.ConfigParser()
if CONFIG_INI_PATH.exists():
    config_parser.read(str(CONFIG_INI_PATH))

# Database configuration (Env overrides settings.ini)
DB_HOST = os.getenv("FRS_DB_HOST", "localhost")
DB_USER = os.getenv("FRS_DB_USER", "root")
DB_PASSWORD = os.getenv("FRS_DB_PASSWORD", "cairo$123")
DB_NAME = os.getenv(
    "FRS_DB_NAME",
    config_parser.get("MYSQL_DB_NAME", "DB_NAME", fallback="cairo_face_recognition")
)

# API Server configuration (Supports Render's dynamic $PORT)
API_HOST = os.getenv("FRS_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("FRS_API_PORT", "8000")))
API_TITLE = "Cairo Face Recognition Engine API"
API_VERSION = "v1"
ADMIN_SECRET = os.getenv("FRS_ADMIN_SECRET", "cairo_frs_master_secret_2026")

# Model Paths
DEFAULT_PROTOTEXT = BASE_DIR / "Detection" / "FRS_MODEL" / "deploy_prototext.txt"
DEFAULT_CAFFE_MODEL = BASE_DIR / "Detection" / "FRS_MODEL" / "face_caffe_model"

PROTOTEXT_PATH = os.getenv(
    "FRS_PROTOTEXT_PATH",
    str(BASE_DIR / config_parser.get("PROTOTEXT_FILE_PATH", "PROTOTEXT_FILE", fallback=str(DEFAULT_PROTOTEXT)))
)

CAFFE_MODEL_PATH = os.getenv(
    "FRS_CAFFE_MODEL_PATH",
    str(BASE_DIR / config_parser.get("RESNET_MODEL_PATH", "RESNET_MODEL", fallback=str(DEFAULT_CAFFE_MODEL)))
)

# Recognition Thresholds
DEFAULT_TOLERANCE = float(os.getenv("FRS_RECOGNITION_TOLERANCE", "0.40"))
CONFIDENCE_THRESHOLD = float(os.getenv("FRS_CONFIDENCE_THRESHOLD", "0.35"))
DNN_INPUT_SIZE = int(os.getenv("FRS_DNN_INPUT_SIZE", "600"))
