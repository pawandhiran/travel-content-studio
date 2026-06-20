"""Local file serving endpoint for the Electron renderer."""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/local")
async def serve_local_file(path: str = Query(..., description="Absolute path to file")):
    """Serve a local file so the renderer can display images loaded from disk.

    Electron's renderer runs on http://localhost in dev mode, which blocks
    file:// URLs.  This endpoint proxies them through the backend instead.
    """
    file = Path(path)
    if not file.is_absolute() or not file.exists() or not file.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    mime, _ = mimetypes.guess_type(str(file))
    return FileResponse(
        path=str(file),
        media_type=mime or "application/octet-stream",
        filename=file.name,
    )
