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
    "freqs": "showfreqs=s={w}x{h}:mode={mode}:colors={colour}",
    "waves": "showwaves=s={w}x{h}:mode=cline:colors={colour}",
    "volume": "showvolume=w={w}:h={h}:c={colour}:b=0:f=0.6",
}


def _hex(colour: tuple[int, int, int, int]) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in colour[:3])


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
        w=width, h=height, mode=visualiser.mode, colour=_hex(visualiser.colour)
    )
    return (
        f"[1:a]{analysis},format=rgba,"
        f"colorchannelmixer=aa={visualiser.opacity:.3f},"
        # Padded onto a transparent frame-sized canvas, which is what puts it in
        # position and lets the words go on top of it rather than under.
        f"pad={output.width}:{output.height}:{x}:{y}:color=0x00000000[viz];"
        f"[viz][0:v]overlay=0:0:format=auto[out]"
    )
