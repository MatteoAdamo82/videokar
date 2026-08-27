"""Long work, run off the request thread.

Separation takes forty seconds and a render takes minutes, so neither can happen
inside a request. Both report progress the same way and are polled the same way,
which is why this is one small runner rather than two special cases.

Deliberately in-process and in-memory: the server is a local tool serving one
person, and a job queue that outlives the process would be a database to keep
alive for no one.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class Job:
    """One piece of work and how far it has got."""

    id: str
    kind: str
    label: str
    status: str = RUNNING
    progress: float = -1.0
    """0..1, or -1 when the work cannot say how far along it is."""

    message: str = ""
    result: Path | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def update(self, *, message: str | None = None, progress: float | None = None) -> None:
        if message is not None:
            self.message = message
        if progress is not None:
            self.progress = progress

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "result": self.result.name if self.result else None,
            **self.extra,
        }


class Jobs:
    """A handful of background jobs, keyed by id."""

    def __init__(self, keep: int = 20) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._keep = keep

    def start(self, kind: str, label: str, work: Callable[[Job], Path | None]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            for stale in self._order[: -self._keep]:
                self._jobs.pop(stale, None)
            self._order = self._order[-self._keep :]

        def run() -> None:
            try:
                job.result = work(job)
                job.status = DONE
                job.progress = 1.0
            except Exception as exc:  # noqa: BLE001 - the message is the product
                logger.warning("job %s failed: %s", job.id, exc)
                logger.debug("%s", traceback.format_exc())
                job.status = FAILED
                # What the user sees is this string, so it carries the reason
                # rather than a traceback they cannot act on.
                job.error = str(exc) or exc.__class__.__name__

        threading.Thread(target=run, name=f"videokar-{kind}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        return [self._jobs[i] for i in reversed(self._order) if i in self._jobs]

    def running(self, kind: str | None = None) -> list[Job]:
        return [
            job
            for job in self.all()
            if job.status == RUNNING and (kind is None or job.kind == kind)
        ]
