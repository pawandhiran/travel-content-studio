"""Local file serving endpoint for the Electron renderer."""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/files", tags=["files"])

_ALLOWED_PREFIXES: list[Path] | None = None


def _get_allowed_prefixes() -> list[Path]:
    global _ALLOWED_PREFIXES
    if _ALLOWED_PREFIXES is None:
        home = Path.home()
        _ALLOWED_PREFIXES = [
            home,
        ]
    return _ALLOWED_PREFIXES


def _is_path_allowed(resolved: Path) -> bool:
    """Return True only if *resolved* lives under an allowed prefix."""
    for prefix in _get_allowed_prefixes():
        try:
            resolved.relative_to(prefix)
            return True
        except ValueError:
            continue
    return False


@router.get("/local")
async def serve_local_file(path: str = Query(..., description="Absolute path to file")):
    """Serve a local file so the renderer can display images loaded from disk.

    Electron's renderer runs on http://localhost in dev mode, which blocks
    file:// URLs.  This endpoint proxies them through the backend instead.
    """
    file = Path(path).resolve()

    if not file.is_absolute() or not file.exists() or not file.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if not _is_path_allowed(file):
        raise HTTPException(status_code=403, detail="Access denied")

    mime, _ = mimetypes.guess_type(str(file))
    return FileResponse(
        path=str(file),
        media_type=mime or "application/octet-stream",
        filename=file.name,
    )
