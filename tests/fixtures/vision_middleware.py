from __future__ import annotations

from time import perf_counter
from typing import Any, Awaitable, Callable


class OmniVisionTraceMiddleware:
    """Fixture-only ASGI middleware sketch for producing Omni-Vision trace events."""

    def __init__(self, app: Callable[..., Awaitable[None]], sink: list[dict[str, Any]]) -> None:
        self.app = app
        self.sink = sink

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        trace: dict[str, Any] = {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "events": [
                {
                    "event": "request.start",
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                }
            ],
        }

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                trace["status_code"] = message.get("status")
            await send(message)

        await self.app(scope, receive, send_wrapper)
        trace["duration_ms"] = round((perf_counter() - started) * 1000, 3)
        trace["events"].append({"event": "request.end", "status_code": trace.get("status_code")})
        self.sink.append(trace)
