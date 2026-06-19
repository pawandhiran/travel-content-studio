class AppError(Exception):
    """Base application error."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str = "An unexpected error occurred", **kwargs):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail)


class ValidationError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"

    def __init__(self, detail: str = "Validation failed"):
        super().__init__(detail)


class GPUBusyError(AppError):
    status_code = 503
    error_code = "GPU_BUSY"

    def __init__(self, detail: str = "GPU is currently busy, try again later"):
        super().__init__(detail)


class ProcessingError(AppError):
    status_code = 500
    error_code = "PROCESSING_ERROR"

    def __init__(self, detail: str = "Processing failed"):
        super().__init__(detail)


class ExternalServiceError(AppError):
    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"

    def __init__(self, detail: str = "External service unavailable"):
        super().__init__(detail)
