import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import CORS_ORIGINS
from .db import Base, engine
from .routers import academics, accounts, board, messages, people, platform, recovery

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("school")

app = FastAPI(title="School Management API", version="2.0.0", docs_url="/docs")
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
Base.metadata.create_all(engine)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return resp


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.error("unhandled_error", exc_info=exc)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(accounts.router)
app.include_router(platform.router)
app.include_router(people.router)
app.include_router(academics.router)
app.include_router(messages.router)
app.include_router(board.router)
app.include_router(recovery.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
