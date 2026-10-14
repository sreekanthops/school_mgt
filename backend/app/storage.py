"""Image upload storage. Files live outside the web root and are only served through
authenticated endpoints. Only PNG / JPEG / WebP are accepted (checked by magic bytes)."""
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
MAX_IMAGE_BYTES = 3 * 1024 * 1024
EXT_MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def detect(data: bytes) -> Optional[str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def read_image(request: Request) -> tuple[bytes, str]:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image too large (max 3 MB)")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image too large (max 3 MB)")
    ext = detect(bytes(buf))
    if not buf or not ext:
        raise HTTPException(415, "Only PNG, JPEG or WebP images are allowed")
    return bytes(buf), ext


def _safe(rel: str) -> Path:
    root = UPLOAD_DIR.resolve()
    p = (UPLOAD_DIR / rel).resolve()
    if root not in p.parents:
        raise HTTPException(404, "Not found")
    return p


def save(school_id: int, data: bytes, ext: str) -> str:
    rel = f"{school_id}/{uuid.uuid4().hex}.{ext}"
    p = _safe(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return rel


def remove(rel: Optional[str]) -> None:
    if rel:
        try:
            _safe(rel).unlink(missing_ok=True)
        except HTTPException:
            pass


def remove_school(school_id: int) -> None:
    shutil.rmtree(UPLOAD_DIR / str(school_id), ignore_errors=True)


def version(rel: Optional[str]) -> Optional[str]:
    return rel.split("/")[-1][:8] if rel else None


def serve(rel: Optional[str]) -> FileResponse:
    if not rel:
        raise HTTPException(404, "No image")
    p = _safe(rel)
    if not p.exists():
        raise HTTPException(404, "No image")
    return FileResponse(p, media_type=EXT_MIME.get(p.suffix[1:], "application/octet-stream"))
