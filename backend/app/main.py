from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.security import API_TOKEN_HEADER
from app.middleware import BodySizeLimitMiddleware

app = FastAPI(title="Task Planner API", version="0.1.0")
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
# The app is a local single-user tool: refuse hosts that are not loopback.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", API_TOKEN_HEADER],
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
