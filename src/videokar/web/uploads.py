"""Taking a file into the working folder.

The audio, the fonts and the sprites all arrive the same way, and all three
had spelt out the same loop: read in chunks, stop at the limit, and take the
half-written file away again rather than leave it lying there.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from .session import MAX_UPLOAD


async def save_upload(upload: UploadFile, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(destination, "wb") as handle:
        while chunk := await upload.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD:
                handle.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(413, "that file is larger than 200 MB")
            handle.write(chunk)
    return destination
