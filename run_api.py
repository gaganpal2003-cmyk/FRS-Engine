import uvicorn
from api.config import API_HOST, API_PORT

if __name__ == "__main__":
    print("=" * 65)
    print(" Starting Cairo Face Recognition Engine API Server...")
    print(f" Host : http://{API_HOST}:{API_PORT}")
    print(f" Swagger Docs : http://localhost:{API_PORT}/docs")
    print(f" ReDoc Docs   : http://localhost:{API_PORT}/redoc")
    print("=" * 65)
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)
