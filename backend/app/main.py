from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.routes.health import router as health_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.research import router as research_router
from app.api.routes.sop import router as sop_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown hooks."""
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-agent scholarship and master's research platform.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 routes
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(profiles_router, prefix=settings.API_V1_PREFIX)
app.include_router(research_router, prefix=settings.API_V1_PREFIX)
app.include_router(sop_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Root redirect to docs or health info."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "health_check": f"{settings.API_V1_PREFIX}/health",
        "documentation": "/docs",
    }
