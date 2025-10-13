from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import logging
import time

from app.core.config import settings
from app.core.exceptions import FinancialDataException
from app.core.database import create_tables
from app.api.v1.api import api_router
from app.models.schemas import HealthCheck, ErrorResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A comprehensive financial data API powered by yfinance",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Exception handler for custom exceptions
@app.exception_handler(FinancialDataException)
async def financial_data_exception_handler(request: Request, exc: FinancialDataException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            detail=exc.detail,
            status_code=exc.status_code
        ).dict()
    )

# Create database tables on startup (legacy - only needed if using local SQLite for other features)
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup"""
    # Note: Authentication now uses Supabase, so local database tables are optional
    # Only create tables if you need local database for other features
    try:
        create_tables()
        logger.info("Local database tables created successfully (if needed)")
    except Exception as e:
        logger.warning(f"Could not create local database tables: {e}")
        logger.info("This is expected if you're only using Supabase for authentication")

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Stockfolio Financial Data API",
        "version": settings.VERSION,
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get(
    "/health",
    response_model=HealthCheck,
    summary="Health check",
    description="Check if the API is running and healthy"
)
async def health_check():
    """Health check endpoint"""
    return HealthCheck(
        status="healthy",
        version=settings.VERSION,
        timestamp=datetime.now()
    )

@app.get("/api", include_in_schema=False)
async def api_info():
    """API information endpoint"""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "description": "Financial data API powered by yfinance",
        "endpoints": {
            "search": f"{settings.API_V1_STR}/search",
            "stock": f"{settings.API_V1_STR}/stock",
            "health": "/health"
        }
    }

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG,
        log_level="info"
    ) 