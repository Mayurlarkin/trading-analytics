from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import accounts, auth, health, imports, ingest


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Trading Analytics API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(imports.router)
    app.include_router(auth.router)
    app.include_router(accounts.router)
    return app


app = create_app()
