class AppError(Exception):
    """Domain error mapped to an HTTP response by app.main (JSON: {"error": code, "message": ...})."""

    def __init__(self, status_code: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra or {}


def not_found(what: str) -> AppError:
    return AppError(404, "not_found", f"{what} not found")
