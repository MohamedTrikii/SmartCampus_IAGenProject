import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_admin, routes_auth, routes_catalog, routes_chat
from app.core.config import settings
from app.core.errors import install_error_handlers

API_PREFIX = "/api/v1"

if settings.jwt_secret in ("change-me-in-production", "remplacez-par-une-longue-chaine-aleatoire") or len(
    settings.jwt_secret
) < 32:
    logging.getLogger("smartcampus").warning(
        "JWT_SECRET absent ou trop court : définissez une chaîne aléatoire d'au moins 32 caractères dans .env"
    )

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API SmartCampus AI — Sprint 1 : socle technique (sessions, auth, catalogue, chat LLM).",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)


@app.get(f"{API_PREFIX}/health", tags=["santé"])
def health():
    return {"status": "ok"}


app.include_router(routes_auth.router, prefix=API_PREFIX)
app.include_router(routes_catalog.router, prefix=API_PREFIX)
app.include_router(routes_chat.router, prefix=API_PREFIX)
app.include_router(routes_admin.router, prefix=API_PREFIX)
