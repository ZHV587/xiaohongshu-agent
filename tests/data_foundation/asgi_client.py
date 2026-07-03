from __future__ import annotations

from types import TracebackType
from typing import Any

import anyio
import httpx


class ASGIClient:
    """Small sync test client backed by httpx.ASGITransport."""

    def __init__(self, app: Any):
        self._app = app
        self._lifespan_cm: Any | None = None
        self._portal_cm: Any | None = None
        self._portal: Any | None = None

    def __enter__(self) -> ASGIClient:
        self._portal_cm = anyio.from_thread.start_blocking_portal()
        self._portal = self._portal_cm.__enter__()
        self._lifespan_cm = self._app.router.lifespan_context(self._app)
        self._portal.call(self._lifespan_cm.__aenter__)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._portal is None or self._portal_cm is None:
            return

        async def _shutdown() -> None:
            if self._lifespan_cm is not None:
                await self._lifespan_cm.__aexit__(exc_type, exc, tb)
                self._lifespan_cm = None

        try:
            self._portal.call(_shutdown)
        finally:
            self._portal_cm.__exit__(exc_type, exc, tb)
            self._portal = None
            self._portal_cm = None

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def _request() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        if self._portal is not None:
            return self._portal.call(_request)
        return anyio.run(_request)
