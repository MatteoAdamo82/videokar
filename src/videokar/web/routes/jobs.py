"""Background work: what is running, and how far along it is."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..deps import CurrentSession

router = APIRouter(prefix="/api/jobs")


@router.get("")
def list_jobs(session: CurrentSession) -> dict[str, Any]:
    return {"jobs": [job.as_dict() for job in session.jobs.all()]}


@router.get("/{job_id}")
def get_job(job_id: str, session: CurrentSession) -> dict[str, Any]:
    job = session.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job.as_dict()
