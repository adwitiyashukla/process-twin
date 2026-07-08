"""FastAPI app shell. Phase 0 ships /health only; the approvals inbox (§7.5) and
explorer endpoints (§11) mount here in phases 4 and 3 respectively."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="process-twin", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "process-twin"}
