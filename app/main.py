from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.comments import router as comments_router
from app.api.history import router as history_router
from app.api.tickets import router as tickets_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.2.0")

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(tickets_router, prefix="/tickets", tags=["tickets"])
app.include_router(comments_router, prefix="/tickets", tags=["comments"])
app.include_router(history_router, prefix="/tickets", tags=["history"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
