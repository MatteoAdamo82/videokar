"""What the video looks like.

Separate from the pivot document on purpose: the JSON holds when each word is
sung, this holds how it is drawn. Change one without touching the other. In the
next step these become a TOML file with presets; for now they are the defaults
the renderer works from.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

RGBA = tuple[int, int, int, int]

Anchor = Literal["top", "center", "bottom"]
OutputFormat = Literal["mp4", "prores4444", "png"]

# Tried in order when no font file is given. A missing font is a hard error
# rather than a silent fallback to Pillow's bitmap default, which renders at
# roughly ten pixels and would look like a bug.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


@dataclass(frozen=True, slots=True)
class TextStyle:
    """How one voice is drawn."""

    font: str | None = None
    """Path to a .ttf/.otf. None picks the first of FONT_CANDIDATES that exists."""

    size: int = 64
    """Pixels, and fixed. Text that changes size from line to line is the thing
    that makes a karaoke video look broken, so a line too wide for the frame
    wraps. Shrinking is opt-in through `min_scale`."""

    colour_off: RGBA = (150, 140, 170, 255)
    """Not yet sung."""

    colour_on: RGBA = (255, 238, 190, 255)
    """Already sung."""

    outline: RGBA | None = (0, 0, 0, 210)
    outline_width: int = 3
    line_spacing: float = 1.15
    min_scale: float = 1.0
    """Lower bound on shrinking a too-wide line, as a fraction of `size`.

    1.0, the default, means never shrink: a line that does not fit wraps at the
    size you asked for. Set it lower only if you would rather one long line got
    smaller than took two rows — and know that it will then differ in size from
    every other line on screen.
    """


@dataclass(frozen=True, slots=True)
class BallStyle:
    """The thing that bounces."""

    kind: Literal["ball", "sprite", "none"] = "ball"
    radius: int = 16
    colour: RGBA = (255, 120, 70, 255)
    sprite: str | None = None
    """PNG with alpha, used when kind is "sprite"."""

    sprite_scale: float = 1.0
    jump_height: float = 62.0
    """Peak of the arc above the text, in pixels."""

    min_bounce: float = 0.35
    """Shortest a single hop may last, in seconds.

    Words closer together than this share one bounce. Sung words are often only
    tens of milliseconds apart — "I know" is 20ms on the reference track, half a
    frame at 25fps — and a full arc in that time is a vertical twitch, not a
    bounce. Grouping them guarantees every hop lasts at least this long.
    """

    gap_above_text: float = 26.0
    lead_in: float = 1.2
    """Seconds of run-up before the first word of a line."""

    hide_after: float = 2.0
    """Disappear once this many seconds of silence have passed inside a line."""


@dataclass(frozen=True, slots=True)
class Layout:
    anchor: Anchor = "bottom"
    margin_x: int = 96
    margin_y: int = 120
    """Distance from the anchored edge, before the safe area."""

    safe_area: float = 0.05
    """Fraction of each edge kept clear. Broadcast habit, and it keeps text off
    the rounded corners of a phone."""


@dataclass(frozen=True, slots=True)
class Timing:
    lead_in: float = 0.8
    """Seconds a line appears before its first word."""

    hold: float = 1.0
    """Seconds a line stays after its last word."""

    fade: float = 0.35
    """Fade duration. Zero is a hard cut."""


@dataclass(frozen=True, slots=True)
class Output:
    width: int = 1920
    height: int = 1080
    fps: int = 25
    format: OutputFormat = "prores4444"
    background: RGBA = (0, 0, 0, 0)
    """Alpha 0 is a transparent overlay to drop over a clip in an editor."""

    segment_seconds: float = 60.0
    """Rendered in chunks and concatenated, so a long track does not hold one
    ffmpeg process open for its whole duration."""

    audio: bool = True
    """Mux the original audio into the result when the file can be found."""


@dataclass(frozen=True, slots=True)
class Style:
    output: Output = field(default_factory=Output)
    layout: Layout = field(default_factory=Layout)
    timing: Timing = field(default_factory=Timing)
    main: TextStyle = field(default_factory=TextStyle)
    paren: TextStyle | None = None
    """Style for the second voice. None means: main, one size down, dimmer."""

    ball: BallStyle = field(default_factory=BallStyle)

    def voice_style(self, voice: str) -> TextStyle:
        if voice != "paren":
            return self.main
        if self.paren is not None:
            return self.paren
        return replace(
            self.main,
            size=int(self.main.size * 0.72),
            colour_off=(120, 120, 140, 255),
            colour_on=(210, 200, 230, 255),
        )


class FontError(RuntimeError):
    """No usable font file."""


def resolve_font_path(candidate: str | None) -> Path:
    """Find a font file, or say clearly that there is none."""
    if candidate:
        path = Path(candidate).expanduser()
        if not path.exists():
            raise FontError(f"font file not found: {path}")
        return path
    for option in FONT_CANDIDATES:
        path = Path(option)
        if path.exists():
            return path
    raise FontError(
        "no default font found on this system — pass one explicitly with --font"
    )
