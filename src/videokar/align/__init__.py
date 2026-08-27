"""Forced alignment: known words, unknown times."""

from .base import Aligner, AlignmentError, AlignmentResult, WordTiming

__all__ = ["Aligner", "AlignmentError", "AlignmentResult", "WordTiming"]


def get_aligner(name: str = "mms_fa", **kwargs) -> Aligner:
    """Build an aligner by name. Imports lazily so torch stays optional."""
    if name in {"mms_fa", "mms", "default"}:
        from .mms_fa import MMSForcedAligner

        return MMSForcedAligner(**kwargs)
    raise AlignmentError(f"unknown aligner {name!r}")
