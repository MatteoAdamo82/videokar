"""What the video looks like, as a typed schema.

Separate from the pivot document on purpose: that holds when each word is sung,
this holds how it is drawn. Change one without touching the other.

Written as pydantic dataclasses rather than plain ones so the same definitions
serve three jobs at once — frozen values the renderer can rely on, validation
with a message that says which field and why, and a JSON schema. The schema is
what lets the sync view eventually build its own controls from this file instead
of a hand-written form that drifts out of step with it, so fields carry
descriptions and bounds, and anything with a fixed set of choices is a Literal
rather than a free string.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import field
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, PlainSerializer
from pydantic.dataclasses import dataclass

Anchor = Literal["top", "center", "bottom"]
OutputFormat = Literal["mp4", "prores4444", "png"]
BallKind = Literal["ball", "sprite", "none"]
TransitionKind = Literal["fade", "cut"]

_HEX = re.compile(r"^#?(?P<digits>[0-9a-fA-F]{3,8})$")


def _parse_colour(value: object) -> object:
    """Accept "#rrggbb", "#rrggbbaa", "#rgb", or a list of channels.

    Hex first because it is what a colour picker speaks and what anyone editing
    the file by hand expects; the list form stays for the odd computed value.
    """
    if not isinstance(value, str):
        return value
    match = _HEX.match(value.strip())
    if not match:
        raise ValueError(f"{value!r} is not a colour — use '#rrggbb' or '#rrggbbaa'")
    digits = match.group("digits")
    if len(digits) in (3, 4):
        digits = "".join(character * 2 for character in digits)
    if len(digits) not in (6, 8):
        raise ValueError(f"{value!r} is not a colour — 3, 4, 6 or 8 hex digits")
    channels = [int(digits[i : i + 2], 16) for i in range(0, len(digits), 2)]
    if len(channels) == 3:
        channels.append(255)
    return tuple(channels)


def _to_hex(value: tuple[int, int, int, int]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in value)


RGBA = Annotated[
    tuple[int, int, int, int],
    BeforeValidator(_parse_colour),
    PlainSerializer(_to_hex, return_type=str),
    Field(description="Colour as #rrggbb or #rrggbbaa. Alpha 00 is transparent."),
]


@dataclass(frozen=True)
class TextStyle:
    """How one voice is drawn."""

    font: str | None = Field(
        default=None, description="Path to a .ttf/.otf. Empty picks a system sans."
    )
    size: int | None = Field(
        default=None,
        ge=6,
        le=600,
        description=(
            "Pixels, and fixed for the whole video: text that changes size line to line "
            "is what makes a karaoke video look broken. Empty derives it from the frame "
            "height. A line too wide to fit wraps."
        ),
    )
    colour_off: RGBA = (150, 140, 170, 255)
    colour_on: RGBA = (255, 238, 190, 255)
    outline: RGBA | None = Field(
        default=(0, 0, 0, 210), description="Outline colour, or empty for none."
    )
    outline_width: int | None = Field(
        default=None,
        ge=0,
        le=40,
        description="Empty scales it with the text: a 3px outline on a 12px font is a blot.",
    )
    line_spacing: float = Field(default=1.15, gt=0.5, le=3.0)
    min_scale: float = Field(
        default=1.0,
        gt=0.1,
        le=1.0,
        description=(
            "How far a too-wide line may shrink instead of wrapping. 1.0 never shrinks, "
            "which keeps every line the same size."
        ),
    )


PAREN_SCALE = 0.72
PAREN_OFF = (120, 120, 140, 255)
PAREN_ON = (210, 200, 230, 255)


@dataclass(frozen=True)
class VoiceStyle:
    """Overrides for the second voice — the lines written in round brackets.

    Every field is optional and empty means "inherit". The starting point is the
    main voice at PAREN_SCALE and dimmer, so this only has to say what differs.

    An override rather than a second full TextStyle because that was a trap:
    asking for one thing, say a matching size, silently reset everything else to
    the main voice's values and the two voices became indistinguishable.
    """

    font: str | None = None
    size: int | None = Field(default=None, ge=6, le=600, description="Overrides scale.")
    scale: float | None = Field(
        default=None,
        gt=0.1,
        le=3.0,
        description=f"Size relative to the main voice. Empty is {PAREN_SCALE}; 1.0 matches it.",
    )
    colour_off: RGBA | None = None
    colour_on: RGBA | None = None
    outline: RGBA | None = None
    outline_width: int | None = Field(default=None, ge=0, le=40)
    line_spacing: float | None = Field(default=None, gt=0.5, le=3.0)
    min_scale: float | None = Field(default=None, gt=0.1, le=1.0)


@dataclass(frozen=True)
class BallStyle:
    """The thing that bounces."""

    kind: BallKind = "ball"
    radius: int | None = Field(
        default=None, ge=1, le=200, description="Empty scales it with the text."
    )
    colour: RGBA = (255, 120, 70, 255)
    sprite: str | None = Field(
        default=None, description="PNG with alpha, used when kind is 'sprite'."
    )
    sprite_scale: float = Field(default=1.0, gt=0.0, le=10.0)
    jump_height: float | None = Field(
        default=None,
        ge=0.0,
        le=1000.0,
        description=(
            "Peak of the arc above the text, in pixels. Empty is about one line high, "
            "which keeps the ball in frame at any size."
        ),
    )
    min_bounce: float = Field(
        default=0.35,
        ge=0.0,
        le=3.0,
        description=(
            "Shortest a single hop may last. Words closer together than this share one "
            "bounce: sung words are often only tens of milliseconds apart, and a full "
            "arc in that time is a twitch rather than a bounce."
        ),
    )
    gap_above_text: float | None = Field(
        default=None, ge=0.0, le=500.0, description="Empty scales it with the text."
    )
    lead_in: float = Field(
        default=1.2, ge=0.0, le=10.0, description="Seconds of run-up before the first word."
    )
    hide_after: float = Field(
        default=2.0,
        ge=0.0,
        le=60.0,
        description="Silence inside a line after which the ball disappears rather than crawls.",
    )


@dataclass(frozen=True)
class Layout:
    anchor: Anchor = "bottom"
    margin_x: int | None = Field(
        default=None, ge=0, le=2000, description="Empty is a twentieth of the frame width."
    )
    margin_y: int | None = Field(
        default=None, ge=0, le=2000, description="Empty is a ninth of the frame height."
    )
    safe_area: float = Field(
        default=0.05,
        ge=0.0,
        lt=0.45,
        description="Fraction of each edge kept clear, on top of the margins.",
    )


@dataclass(frozen=True)
class Timing:
    lead_in: float = Field(
        default=0.8, ge=0.0, le=10.0, description="Seconds a line appears before its first word."
    )
    hold: float = Field(
        default=1.0, ge=0.0, le=10.0, description="Seconds a line stays after its last word."
    )
    fade: float = Field(default=0.35, ge=0.0, le=5.0, description="Zero is a hard cut.")
    transition: TransitionKind = "fade"


# The NTSC rates are not the decimals people write: 23.976 is 24000/1001. Using
# the rounded decimal puts the drift back, smaller — about two frames over an
# hour — so the fraction is what reaches ffmpeg and what frame times are
# computed from.
NTSC_RATES = {
    Fraction(24000, 1001): 23.976,
    Fraction(30000, 1001): 29.97,
    Fraction(48000, 1001): 47.952,
    Fraction(60000, 1001): 59.94,
    Fraction(120000, 1001): 119.88,
}


def exact_rate(fps: float) -> Fraction:
    """The frame rate as a fraction, recognising the NTSC ones by their decimal."""
    if abs(fps - round(fps)) < 1e-9:
        return Fraction(int(round(fps)), 1)
    for fraction, decimal in NTSC_RATES.items():
        if abs(fps - decimal) < 0.01:
            return fraction
    return Fraction(fps).limit_denominator(100000)


@dataclass(frozen=True)
class Output:
    width: int = Field(default=1920, ge=16, le=16000)
    height: int = Field(default=1080, ge=16, le=16000)
    fps: float = Field(
        default=25,
        gt=0,
        le=240,
        description=(
            "Match your editing timeline. A clip at a rate the project does not use "
            "gets conformed, which reads as the overlay drifting further behind as "
            "the song goes on. 23.976 and 29.97 are understood exactly."
        ),
    )
    format: OutputFormat = "prores4444"
    background: RGBA = Field(
        default=(0, 0, 0, 0), description="Alpha 00 is a transparent overlay for an editor."
    )
    segment_seconds: float = Field(
        default=60.0,
        gt=1.0,
        le=3600.0,
        description=(
            "Rendered in chunks and concatenated, so one long ffmpeg run cannot lose it all."
        ),
    )
    audio: bool = Field(
        default=True,
        description=(
            "Mux the song into the result. Worth leaving on even for an overlay: a "
            "clip that carries its own audio lines itself up in an editor, and cannot "
            "drift away from it."
        ),
    )

    @property
    def rate(self) -> Fraction:
        """The frame rate as an exact fraction."""
        return exact_rate(self.fps)

    def frame_time(self, index: int) -> float:
        """When frame `index` is shown, computed from the exact rate."""
        return float(index / self.rate)

    def frame_count(self, duration: float) -> int:
        return int(round(duration * float(self.rate)))


# Ratios read off the values that were tuned by eye at 1920x1080, so a default
# render there is unchanged and every other size now follows it. Absolute pixels
# were fine until the first small frame: at 320x180 the margins alone left 96
# pixels of usable width, and the ball's arc put it eighty pixels above the top
# of the picture.
_MARGIN_X = 0.05
_MARGIN_Y = 1 / 9
_OUTLINE = 1 / 21
_BALL_RADIUS = 0.25
_BALL_JUMP = 0.97
_BALL_GAP = 0.41


def resolved_size(text: TextStyle, output: Output) -> int:
    """The font size actually used: explicit, or derived from the frame height.

    Tying the default to the height means a preset looks the same at 720p and at
    4K without carrying a size per resolution. It is still one fixed size for the
    whole render.
    """
    if text.size is not None:
        return text.size
    return max(12, round(output.height / 17))


def resolved_margins(layout: Layout, output: Output) -> tuple[int, int]:
    """Margins in pixels: explicit, or a fraction of the frame."""
    return (
        layout.margin_x if layout.margin_x is not None else round(output.width * _MARGIN_X),
        layout.margin_y if layout.margin_y is not None else round(output.height * _MARGIN_Y),
    )


def resolved_outline(text: TextStyle, size: int) -> int:
    if text.outline_width is not None:
        return text.outline_width
    return max(1, round(size * _OUTLINE))


@dataclasses.dataclass(frozen=True, slots=True)
class Ball:
    """A BallStyle with every dimension settled into pixels.

    A separate type from BallStyle on purpose: the configured one has optional
    sizes meaning "work it out from the text", and doing arithmetic on those
    is a None away from a crash. Anything that draws takes this.
    """

    kind: BallKind
    colour: RGBA
    radius: int
    jump_height: float
    gap_above_text: float
    min_bounce: float
    lead_in: float
    hide_after: float
    sprite: str | None = None
    sprite_scale: float = 1.0


def resolved_ball(ball: BallStyle, size: int) -> Ball:
    """Settle a ball's dimensions against the text size.

    Against the text rather than the frame: the ball has to look right next to
    the words it is bouncing on, and those already follow the frame.
    """
    return Ball(
        kind=ball.kind,
        colour=ball.colour,
        radius=ball.radius if ball.radius is not None else max(2, round(size * _BALL_RADIUS)),
        jump_height=(
            ball.jump_height if ball.jump_height is not None else round(size * _BALL_JUMP, 1)
        ),
        gap_above_text=(
            ball.gap_above_text
            if ball.gap_above_text is not None
            else round(size * _BALL_GAP, 1)
        ),
        min_bounce=ball.min_bounce,
        lead_in=ball.lead_in,
        hide_after=ball.hide_after,
        sprite=ball.sprite,
        sprite_scale=ball.sprite_scale,
    )


@dataclass(frozen=True)
class Style:
    """Everything about how the video looks."""

    output: Output = field(default_factory=Output)
    layout: Layout = field(default_factory=Layout)
    timing: Timing = field(default_factory=Timing)
    main: TextStyle = field(default_factory=TextStyle)
    paren: VoiceStyle = Field(
        default_factory=VoiceStyle,
        description=(
            "The second voice — the parenthesised lines. Only what differs from the "
            "main voice, which it otherwise follows one size down and dimmer."
        ),
    )
    ball: BallStyle = field(default_factory=BallStyle)

    def voice_style(self, voice: str) -> TextStyle:
        """The text style for a voice, with the second voice's overrides applied.

        The second voice starts from the main one, scaled down and dimmed, and
        the override only replaces what it actually names.
        """
        if voice != "paren":
            return self.main

        override = self.paren
        if override.size is not None:
            size = override.size
        else:
            scale = override.scale if override.scale is not None else PAREN_SCALE
            size = max(6, round(resolved_size(self.main, self.output) * scale))

        named = {
            field_name: value
            for field_name in (
                "font",
                "colour_off",
                "colour_on",
                "outline",
                "outline_width",
                "line_spacing",
                "min_scale",
            )
            if (value := getattr(override, field_name)) is not None
        }
        return dataclasses.replace(
            self.main,
            size=size,
            colour_off=named.pop("colour_off", PAREN_OFF),
            colour_on=named.pop("colour_on", PAREN_ON),
            **named,
        )

    def resolved_size(self, style: TextStyle) -> int:
        return resolved_size(style, self.output)
