from __future__ import annotations

import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from data_foundation.internal_api import internal_routes
from data_foundation.runtime_facts import create_runtime_snapshot, utc_now
from data_foundation.supervisor import build_supervisor


def shutdown_grace_seconds() -> float:
    return float(os.environ.get("XHS_SCHEDULER_SHUTDOWN_GRACE_SECONDS", "10"))


async def ok(_request):
    return JSONResponse({"ok": True})


@asynccontextmanager
async def lifespan(app: Starlette):
    supervisor = build_supervisor()
    await supervisor.start()
    runtime_snapshot = create_runtime_snapshot(supervisor)
    app.state.supervisor = supervisor
    app.state.runtime_snapshot = runtime_snapshot
    try:
        yield {"supervisor": supervisor, "runtime_snapshot": runtime_snapshot}
    finally:
        await supervisor.stop(grace_seconds=shutdown_grace_seconds())
        runtime_snapshot.stop(observed_at=utc_now())
        app.state.supervisor = None
        app.state.runtime_snapshot = None


app = Starlette(routes=[Route("/ok", ok), *internal_routes], lifespan=lifespan)
