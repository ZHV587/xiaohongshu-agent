from __future__ import annotations

import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from data_foundation.supervisor import build_supervisor


def shutdown_grace_seconds() -> float:
    return float(os.environ.get("XHS_SCHEDULER_SHUTDOWN_GRACE_SECONDS", "10"))


async def ok(_request):
    return JSONResponse({"ok": True})


@asynccontextmanager
async def lifespan(_app: Starlette):
    supervisor = build_supervisor()
    await supervisor.start()
    try:
        yield {"supervisor": supervisor}
    finally:
        await supervisor.stop(grace_seconds=shutdown_grace_seconds())


app = Starlette(routes=[Route("/ok", ok)], lifespan=lifespan)
