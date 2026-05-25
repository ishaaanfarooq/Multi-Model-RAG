import os
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from utils.logger_config import setup_logging
import logging

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Multi-Model RAG System API")

# Setup CORS - supports env var for production and localhost for dev
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

# Ensure uploads directory exists with proper error handling
try:
    os.makedirs("uploads", exist_ok=True)
    logger.info("Uploads directory initialized successfully.")
except Exception as e:
    logger.error(f"Failed to create uploads directory: {e}")
    raise

try:
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
except Exception as e:
    logger.error(f"Failed to mount uploads directory: {e}")
    raise

@app.get("/")
def read_root():
    return {"message": "Welcome to the Multi-Model RAG API", "status": "running", "version": "1.0.0"}

@app.get("/health")
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    return {"status": "healthy", "version": "1.0.0"}
    
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BACKEND_PORT", 8000))
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    logger.info(f"Starting FastAPI server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
