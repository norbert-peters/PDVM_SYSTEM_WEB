"""
PDVM System Web - FastAPI Application
Main entry point for the backend API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import DatabasePool
from app.api import auth, tables, admin, mandanten, menu, gcs

app = FastAPI(
    title="PDVM System API",
    description="Business Management System API",
    version="1.0.0"
)

# Startup/Shutdown events
@app.on_event("startup")
async def startup():
    """Initialize database pools on startup"""
    await DatabasePool.create_pool()
    print("✅ Database pools initialized")

@app.on_event("shutdown")
async def shutdown():
    """Close database pools on shutdown"""
    await DatabasePool.close_pool()
    print("✅ Database pools closed")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(mandanten.router, prefix="/api/mandanten", tags=["Mandanten"])
app.include_router(menu.router, prefix="/api/menu", tags=["Menu"])
app.include_router(gcs.router, prefix="/api/gcs", tags=["GCS"])
app.include_router(tables.router, prefix="/api/tables", tags=["Tables"])
app.include_router(admin.router, prefix="/api/admin", tags=["Administration"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "PDVM System API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
