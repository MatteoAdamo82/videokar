"""The band that reacts to the music.

Built as an ffmpeg filter rather than drawn here. Those filters have had twenty
years of work put into them and there is no reason to write another FFT; what
this module decides is where the band goes, how big it is, and that it ends up
*under* the words rather than over them.

The last part is the whole trick. The obvious chain overlays the analysis onto
the karaoke frames, which puts a spectrum on top of the lyrics. Instead the
analysis is padded out to the full frame on a transparent canvas and the karaoke
frames are laid over that.
"""

from __future__ import annotations

from ..config.schema import Output, Visualiser

FILTERS = {
    # fscale=log because music is logarithmic in pitch: on a linear axis
    # everything anyone sings is crushed into the left fifth of the band and the
    # rest is empty. win_size and averaging trade a little sharpness for bars
    # that do not flicker frame to frame.
    "freqs": (
        "showfreqs=s={w}x{h}:mode={mode}:colors={colour}"
        ":fscale=log:ascale=log:win_size=2048:averaging=3"
    ),
    # rate tied to the video's own frame rate so each frame holds exactly one
    # frame's worth of audio. Left to itself showwaves accumulates a scrolling
    # history, which starts empty — and starts empty again at every segment
    # boundary, so the waveform kept sliding in from the right.
    "waves": (
        "showwaves=s={w}x{h}:mode=cline:colors={colour}:scale=sqrt:draw=full:r={fps}"
    ),
    # showvolume's `c` is not a colour but an expression evaluated per channel,
    # so it rejects "#ffffff" outright — and the number it wants is packed
    # AABBGGRR rather than the usual order. t and v turn off the channel names
    # and the decibel readout, which belong on a mixing desk, not over lyrics.
    # Segmented rather than one solid slab, which is what a meter looks like
    # and what stops it reading as a grey rectangle behind the words.
    "volume": "showvolume=w={w}:h={h}:c={packed}:b=1:f=0.6:t=0:v=0:s=3:o=h",
}


def _hex(colour: tuple[int, int, int, int]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in colour[:3])


def _packed(colour: tuple[int, int, int, int]) -> str:
    """The same colour as the number showvolume's expression wants: AABBGGRR."""
    red, green, blue, alpha = colour
    return f"0x{alpha:02x}{blue:02x}{green:02x}{red:02x}"


def placement(visualiser: Visualiser, output: Output) -> tuple[int, int, int, int]:
    """Size and position of the band in pixels: width, height, x, y."""
    width = max(2, round(output.width * visualiser.width))
    height = max(2, round(output.height * visualiser.height))
    margin = round(output.height * visualiser.margin)
    x = (output.width - width) // 2
    if visualiser.anchor == "top":
        y = margin
    elif visualiser.anchor == "center":
        y = (output.height - height) // 2
    else:
        y = output.height - height - margin
    return width, height, x, y


def filter_chain(visualiser: Visualiser, output: Output) -> str | None:
    """The filter_complex that draws the band under the karaoke frames.

    Expects the karaoke frames as input 0 and the audio as input 1, and produces
    a label named `out`. None when there is nothing to draw.
    """
    if visualiser.kind == "none":
        return None
    width, height, x, y = placement(visualiser, output)
    analysis = FILTERS[visualiser.kind].format(
        w=width,
        h=height,
        mode=visualiser.mode,
        colour=_hex(visualiser.colour),
        packed=_packed(visualiser.colour),
        fps=f"{output.rate.numerator}/{output.rate.denominator}",
    )
    return (
        f"[1:a]{analysis},format=rgba,"
        # Scaled to the box rather than trusted to come out at the size it was
        # asked for: each of these filters lays itself out its own way — one
        # stacks a row per channel, another leaves most of its canvas empty —
        # so without this the band lands off-centre or over the edge.
        f"scale={width}:{height},"
        f"colorchannelmixer=aa={visualiser.opacity:.3f},"
        # Padded onto a transparent frame-sized canvas, which is what puts it in
        # position and lets the words go on top of it rather than under.
        f"pad={output.width}:{output.height}:{x}:{y}:color=0x00000000[viz];"
        # shortest=1 because the base here is the analysis, which runs to the
        # end of the song, while the frames are one segment long. Without it the
        # output lasts as long as the audio and overlay repeats the last frame
        # it was given — the words freeze on whatever line the segment ended on
        # and stay there for the rest of the video.
        f"[viz][0:v]overlay=0:0:format=auto:shortest=1[out]"
    )
