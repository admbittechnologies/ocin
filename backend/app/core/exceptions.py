from fastapi import HTTPException, status


class UnauthorizedException(HTTPException):
    """401 Unauthorized"""

    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": detail, "code": "UNAUTHORIZED"})


class ForbiddenException(HTTPException):
    """403 Forbidden"""

    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail={"error": detail, "code": "FORBIDDEN"})


class BadRequestException(HTTPException):
    """400 Bad Request"""

    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": detail, "code": "BAD_REQUEST"})


class NotFoundException(HTTPException):
    """404 Not Found"""

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail={"error": detail, "code": "NOT_FOUND"})


class ConflictException(HTTPException):
    """409 Conflict"""

    def __init__(self, detail: str = "Resource conflict"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail={"error": detail, "code": "CONFLICT"})


class RateLimitExceededException(HTTPException):
    """429 Too Many Requests"""

    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"error": detail, "code": "RATE_LIMIT_EXCEEDED"})


class ToolUnavailableException(HTTPException):
    """Tool execution failed"""

    def __init__(self, detail: str = "Tool unavailable"):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": detail, "code": "TOOL_ERROR"})


class ScheduleParseException(HTTPException):
    """Schedule parsing failed"""

    def __init__(self, detail: str = "Could not understand schedule"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": detail, "code": "SCHEDULE_PARSE_ERROR"})


class ApprovalRequestedException(HTTPException):
    """Raised when an agent requests approval but execution should pause."""

    def __init__(self, approval_id: str, message: str = "Approval requested"):
        self.approval_id = approval_id
        self.message = message
        super().__init__(status_code=status.HTTP_200_OK, detail={"approval_id": approval_id, "message": message})
