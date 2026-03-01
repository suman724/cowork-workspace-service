"""Service-level exceptions mapped to standard error codes."""

from __future__ import annotations


class ServiceError(Exception):
    """Base for all workspace service errors."""

    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(ServiceError):
    """Resource not found."""

    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message, code="NOT_FOUND", status_code=404)


class WorkspaceNotFoundError(ServiceError):
    """Workspace not found."""

    def __init__(self, workspace_id: str = "") -> None:
        msg = f"Workspace not found: {workspace_id}" if workspace_id else "Workspace not found"
        super().__init__(msg, code="WORKSPACE_NOT_FOUND", status_code=404)


class ArtifactNotFoundError(ServiceError):
    """Artifact not found."""

    def __init__(self, artifact_id: str = "") -> None:
        msg = f"Artifact not found: {artifact_id}" if artifact_id else "Artifact not found"
        super().__init__(msg, code="FILE_NOT_FOUND", status_code=404)


class ArtifactTooLargeError(ServiceError):
    """Artifact exceeds size limit."""

    def __init__(self, size: int = 0, limit: int = 0) -> None:
        msg = f"Artifact too large: {size} bytes (limit {limit})"
        super().__init__(msg, code="FILE_TOO_LARGE", status_code=413)


class ValidationError(ServiceError):
    """Request validation failed."""

    def __init__(self, message: str = "Invalid request") -> None:
        super().__init__(message, code="INVALID_REQUEST", status_code=400)


class StorageError(ServiceError):
    """S3 or DynamoDB operation failed."""

    def __init__(self, message: str = "Storage operation failed") -> None:
        super().__init__(message, code="WORKSPACE_UPLOAD_FAILED", status_code=502)
