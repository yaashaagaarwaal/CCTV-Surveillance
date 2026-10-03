from fastapi import APIRouter, Depends

from app.core.config import settings
from app.security.deps import current_user

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(current_user)])

VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


@router.get("/files")
def list_video_files():
    """Video files that can be used as a looping "file" camera source."""
    folder = settings.video_sources_dir
    folder.mkdir(parents=True, exist_ok=True)
    files = sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES)
    return {"directory": str(folder), "files": files}
