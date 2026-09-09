"""Frames to a file, through ffmpeg.

Raw RGBA is piped straight into ffmpeg rather than written to disk as PNGs: at
1080p a three minute video is around 45 GB of intermediate frames, and the pipe
costs nothing.

Long renders go out in segments and are concatenated with a stream copy. One
ffmpeg process held open for the whole track is the version that loses an hour
of work to a broken pipe at minute nine.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from ..audio.io import require_ffmpeg
from ..config.schema import Background, Output

logger = logging.getLogger(__name__)


class EncodeError(RuntimeError):
    """ffmpeg refused the frames."""


@dataclass(frozen=True, slots=True)
class Codec:
    args: list[str]
    suffix: str
    keeps_alpha: bool


CODECS: dict[str, Codec] = {
    # ProRes 4444 is the reason this tool exists: an overlay with a real alpha
    # channel that drops straight onto a clip in Final Cut.
    "prores4444": Codec(
        args=["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"],
        suffix=".mov",
        keeps_alpha=True,
    ),
    "mp4": Codec(
        args=["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium"],
        suffix=".mp4",
        keeps_alpha=False,
    ),
    # Both lossless, both carry alpha, and both a fraction of the size for this
    # kind of picture — flat colour over a transparent field is the worst case
    # for an intra-frame DCT codec and the best case for these. Neither decodes
    # appreciably slower than ProRes, which was the thing worth checking.
    "animation": Codec(
        args=["-c:v", "qtrle", "-pix_fmt", "argb"], suffix=".mov", keeps_alpha=True
    ),
    "png_mov": Codec(
        args=["-c:v", "png", "-pix_fmt", "rgba"], suffix=".mov", keeps_alpha=True
    ),
    "png": Codec(args=["-c:v", "png"], suffix="", keeps_alpha=True),
}


def _flatten(frame: Image.Image, background: tuple[int, int, int, int]) -> Image.Image:
    """Composite onto an opaque background for a format with no alpha."""
    base = Image.new("RGBA", frame.size, (*background[:3], 255))
    base.alpha_composite(frame)
    return base


def _background_args(
    background: Background, output: Output, offset: float
) -> tuple[list[str], list[str]]:
    """ffmpeg's inputs and filter for a clip behind the overlay.

    Composited here rather than in Pillow: ffmpeg is already in the pipeline and
    already decodes video, and pulling frames into Python to paste them one at a
    time would be the slow way round.

    The offset is taken with `trim`, not by seeking the input. Seeking into a
    stream that is also being looped does not land where the arithmetic says it
    should, and the drift only shows up segments later, as a background that
    slips further out of step the longer the song runs. Trimming costs the
    decode of the frames it throws away, which for a short clip is nothing next
    to drawing the frames themselves.
    """
    clip = Path(background.video)
    if not clip.is_file():
        raise EncodeError(f"the background video {clip.name} is not there")

    inputs = ["-stream_loop", "-1"] if background.loop else []
    inputs += ["-i", str(clip)]

    steps = []
    if not background.loop:
        # Hold the last frame rather than running out and leaving black.
        steps.append("tpad=stop=-1:stop_mode=clone")
    if offset:
        steps += [f"trim=start={offset:.3f}", "setpts=PTS-STARTPTS"]
    steps.append(
        {
            "cover": (
                f"scale={output.width}:{output.height}:force_original_aspect_ratio=increase,"
                f"crop={output.width}:{output.height}"
            ),
            "contain": (
                f"scale={output.width}:{output.height}:force_original_aspect_ratio=decrease,"
                f"pad={output.width}:{output.height}:-1:-1:color=black"
            ),
            "stretch": f"scale={output.width}:{output.height}",
        }[background.fit]
    )
    if background.dim:
        keep = 1 - background.dim
        steps.append(f"colorchannelmixer=rr={keep}:gg={keep}:bb={keep}")
    steps.append("setsar=1")

    chain = (
        f"[1:v]{','.join(steps)}[bg];"
        # shortest: the overlay is exactly as long as the song, and without this
        # a looping clip would keep the encoder running for ever.
        "[bg][0:v]overlay=shortest=1,format=yuv420p[v]"
    )
    return inputs, ["-filter_complex", chain, "-map", "[v]"]


def render_frames(
    frames: Iterator[Image.Image],
    destination: Path,
    output: Output,
    *,
    audio_path: Path | None = None,
    audio_offset: float = 0.0,
    mux_audio: bool = True,
    background: Background | None = None,
    background_offset: float = 0.0,
) -> Path:
    """Pipe frames into one ffmpeg process and write a single file."""
    require_ffmpeg()
    codec = CODECS[output.format]
    keep_alpha = codec.keeps_alpha and output.background[3] < 255
    behind = background if background and background.video else None
    if behind:
        # The frames are drawn see-through so the clip shows; flattening them
        # onto the preset's colour first would hide it completely.
        keep_alpha = True

    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{output.width}x{output.height}",
        "-r", f"{output.rate.numerator}/{output.rate.denominator}",
        "-i", "-",
    ]  # fmt: skip
    # The clip is input 1, so the audio that used to be it becomes input 2.
    filters: list[str] = []
    if behind:
        clip_inputs, filters = _background_args(behind, output, background_offset)
        command += clip_inputs
    audio_input = 2 if behind else 1
    if audio_path is not None:
        command += ["-ss", f"{audio_offset:.3f}", "-i", str(audio_path)]
    if filters:
        command += filters
    elif audio_path is not None and mux_audio:
        command += ["-map", "0:v:0"]
    command += codec.args
    if audio_path is not None and mux_audio:
        command += ["-c:a", "aac", "-b:a", "192k", "-map", f"{audio_input}:a:0", "-shortest"]
    command.append(str(destination))

    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None and process.stderr is not None

    expected = (output.width, output.height)
    broken = False
    try:
        for frame in frames:
            if frame.size != expected:
                # Raw video carries no framing, so ffmpeg would accept the bytes
                # and produce a smeared, diagonally torn video rather than fail.
                raise EncodeError(
                    f"frame is {frame.size[0]}x{frame.size[1]}, "
                    f"expected {output.width}x{output.height}"
                )
            if not keep_alpha:
                frame = _flatten(frame, output.background)
            process.stdin.write(frame.tobytes())
    except BrokenPipeError:
        # ffmpeg exited mid-stream. Its own stderr says why; raise that rather
        # than the write error, which only ever says "broken pipe".
        broken = True
    except EncodeError:
        process.kill()
        raise
    finally:
        # Closed by hand rather than through communicate(): communicate() would
        # try to flush a pipe that is already gone.
        if not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                broken = True

    stderr = process.stderr.read().decode(errors="replace").strip()
    process.stderr.close()
    process.wait()

    if broken:
        raise EncodeError(f"ffmpeg stopped early: {stderr or 'no output'}")
    if process.returncode != 0:
        raise EncodeError(f"ffmpeg failed: {stderr or 'no output'}")
    return destination


def render_png_sequence(
    frames: Iterator[Image.Image],
    directory: Path,
    *,
    start_frame: int = 0,
    stem: str = "frame",
) -> Path:
    """Write a numbered PNG per frame. Alpha is preserved as-is."""
    directory.mkdir(parents=True, exist_ok=True)
    for offset, frame in enumerate(frames):
        frame.save(directory / f"{stem}_{start_frame + offset:06d}.png")
    return directory


def render_segmented(
    frame_at: Callable[[float], Image.Image],
    destination: Path,
    output: Output,
    *,
    start: float,
    end: float,
    audio_path: Path | None = None,
    background: Background | None = None,
    on_segment: Callable[[int, int], None] | None = None,
) -> Path:
    """Render [start, end) in segments and concatenate them.

    Frame times are computed from the absolute frame index rather than
    accumulated per segment, so a segment boundary cannot drift the timing, and
    from the exact rate rather than the decimal people write it as.
    """
    require_ffmpeg()
    codec = CODECS[output.format]
    rate = float(output.rate)
    first_frame = int(round(start * rate))
    last_frame = int(round(end * rate))
    per_segment = max(1, int(output.segment_seconds * rate))
    boundaries = list(range(first_frame, last_frame, per_segment))

    if len(boundaries) <= 1:
        frames = (frame_at(output.frame_time(index)) for index in range(first_frame, last_frame))
        if on_segment:
            on_segment(1, 1)
        return render_frames(
            frames,
            destination,
            output,
            audio_path=audio_path,
            audio_offset=start,
            background=background,
            background_offset=start,
        )

    with TemporaryDirectory(prefix="videokar-segments-") as workdir:
        parts: list[Path] = []
        for number, segment_start in enumerate(boundaries, start=1):
            segment_end = min(segment_start + per_segment, last_frame)
            part = Path(workdir) / f"part{number:04d}{codec.suffix}"
            frames = (
                frame_at(output.frame_time(index))
                for index in range(segment_start, segment_end)
            )
            # Audio is muxed once, onto the concatenated result: a per-segment
            # mux would re-encode the same audio a dozen times and put an AAC
            # priming delay at every seam.
            # Each segment seeks the clip to where it actually begins, so the
            # background carries on across a seam rather than restarting at it.
            render_frames(
                frames,
                part,
                output,
                background=background,
                background_offset=segment_start / rate,
            )
            parts.append(part)
            if on_segment:
                on_segment(number, len(boundaries))

        listing = Path(workdir) / "parts.txt"
        listing.write_text("".join(f"file '{part}'\n" for part in parts), encoding="utf-8")
        joined = destination if audio_path is None else Path(workdir) / f"joined{codec.suffix}"
        _concat(listing, joined)
        if audio_path is not None:
            _mux_audio(joined, audio_path, destination, start)
    return destination


def _run(command: list[str], what: str) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise EncodeError(f"{what} failed: {result.stderr.strip()}")


def _concat(listing: Path, destination: Path) -> None:
    _run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c", "copy", str(destination),
        ],
        "concat",
    )  # fmt: skip


def _mux_audio(video: Path, audio: Path, destination: Path, offset: float) -> None:
    _run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(video), "-ss", f"{offset:.3f}", "-i", str(audio),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0", "-shortest", str(destination),
        ],
        "audio mux",
    )  # fmt: skip


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None
