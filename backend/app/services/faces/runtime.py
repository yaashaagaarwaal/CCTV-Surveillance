from app.services.faces.service import FaceService

# The one FaceService instance, created at startup and shared by the camera
# pipelines and the registration API. None when disabled or unavailable.
_service: FaceService | None = None


def set_face_service(service: FaceService | None) -> None:
    global _service
    _service = service


def get_face_service() -> FaceService | None:
    return _service
