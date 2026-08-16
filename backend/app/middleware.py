from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class BodySizeLimitMiddleware:
    """Reject oversized request bodies before they reach the application.

    Requests must declare a Content-Length: the API is only used by the bundled
    web client, and refusing undeclared (chunked) bodies keeps the check simple
    and impossible to bypass by streaming.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is None:
            if scope["method"] in BODY_METHODS and headers.get("transfer-encoding"):
                await PlainTextResponse("Length required", status_code=411)(
                    scope, receive, send
                )
                return
        elif not declared.isdigit() or int(declared) > self.max_bytes:
            await PlainTextResponse("Request body too large", status_code=413)(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)
