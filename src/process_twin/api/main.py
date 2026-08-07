"""FastAPI app. /health from phase 0; explorer endpoints from phase 3; the approvals"""

from __future__ import annotations

from fastapi import FastAPI

from process_twin.api.approvals import router as approvals_router
from process_twin.api.explorer import router as explorer_router

app = FastAPI(title="process-twin", version="0.1.0")
app.include_router(explorer_router)
app.include_router(approvals_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "process-twin"}
