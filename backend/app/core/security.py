import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings

API_TOKEN_HEADER = "X-Task-Planner-Token"  # noqa: S105 - header name, not a secret


def require_api_token(
    x_task_planner_token: str | None = Header(default=None),
) -> None:
    """Optional shared-secret guard.

    The application is a single-user local tool, so the token stays disabled
    unless TASK_PLANNER_API_TOKEN is set. When it is set, every API request
    must present it.
    """
    expected = settings.api_token
    if not expected:
        return
    if x_task_planner_token is None or not hmac.compare_digest(
        x_task_planner_token, expected
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API token")
