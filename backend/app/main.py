from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from .config import get_settings
from .database import create_tables
from .routers import financial_router
from .services.scheduler import start_scheduler, shutdown_scheduler, sync_vn50_symbols

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: Create database tables and start scheduler
    create_tables()
    start_scheduler()

    # Start VN50 sync in background (don't block startup)
    asyncio.create_task(sync_vn50_symbols())

    yield
    # Shutdown: Clean up resources
    shutdown_scheduler()


app = FastAPI(
    title=settings.app_name,
    description="API for fetching and storing Vietnam stock financial reports using vnstock3",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(financial_router, prefix="/api", tags=["Financial Reports"])


@app.get("/")
async def root():
    """Root endpoint - API health check."""
    return {
        "message": "Vietnam Stock Financial Reports API",
        "status": "healthy",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for deployment."""
    return {"status": "healthy"}
