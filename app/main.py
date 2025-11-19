from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from app.core.config import settings
from app.core.database import engine, Base
from app.api.routes import auth, folders, documents, chat, webhooks, admin
from app.services.azure_blob import blob_service

# Configure Application Insights if available
appinsights_key = os.getenv("APPINSIGHTS_INSTRUMENTATIONKEY")
if appinsights_key:
    try:
        from opencensus.ext.azure.log_exporter import AzureLogHandler
        from opencensus.ext.azure.trace_exporter import AzureExporter
        from opencensus.trace.samplers import ProbabilitySampler
        from opencensus.trace import config_integration

        # Configure tracing
        config_integration.trace_integrations(['logging', 'requests'])

        # Configure logging with Application Insights
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                AzureLogHandler(connection_string=f"InstrumentationKey={appinsights_key}")
            ]
        )
        logger = logging.getLogger(__name__)
        logger.info("Application Insights logging configured")
    except Exception as e:
        # Fallback to standard logging if Application Insights fails
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to configure Application Insights: {e}")
else:
    # Standard logging if no Application Insights key
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    import asyncio

    # Startup
    logger.info("Starting up application...")

    # Start background initialization tasks
    async def initialize_resources():
        """Initialize database and blob storage in background."""
        # Create database tables
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables created successfully")
        except Exception as e:
            logger.error(f"⚠️ Failed to create database tables: {e}")

        # Ensure blob storage containers exist
        try:
            await blob_service.ensure_containers_exist()
            logger.info("✅ Blob storage containers verified")
        except Exception as e:
            logger.error(f"⚠️ Failed to verify blob storage containers: {e}")

        logger.info("🚀 Background initialization complete")

    # Start initialization in background without waiting
    asyncio.create_task(initialize_resources())

    # Start document indexing worker
    worker_task = None
    try:
        from worker.document_indexing_worker import document_worker
        worker_task = asyncio.create_task(document_worker.start())
        logger.info("✅ Document indexing worker started")
    except Exception as e:
        logger.error(f"⚠️ Failed to start document indexing worker: {e}")

    logger.info("Application ready to accept requests")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Stop worker gracefully
    if worker_task:
        logger.info("Stopping document indexing worker...")
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            logger.info("✅ Document indexing worker stopped")
        except Exception as e:
            logger.error(f"Error stopping worker: {e}")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="RAG-based document analysis API with Azure AI services",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
# Support both explicit origins and wildcard patterns for Lovable deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https://.*\.lovable\.(app|dev)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(folders.router, prefix=settings.API_V1_PREFIX)
app.include_router(documents.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
app.include_router(webhooks.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "RAG Document Analysis API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development"
    )
