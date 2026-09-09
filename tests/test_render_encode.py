import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

from videokar.config.schema import Background, Output
from videokar.render.encode import (
    CODECS,
    EncodeError,
    _flatten,
    have_ffmpeg,
    render_frames,
    render_png_sequence,
    render_segmented,
)

needs_ffmpeg = pytest.mark.skipif(not have_ffmpeg(), reason="ffmpeg is not on PATH")

# Segments have a one-second floor in the schema, so the window is sized to
# produce several of them rather than the floor being lowered for a test.
TINY = Output(width=32, height=32, fps=10, segment_seconds=1.5)


def frame(shade: int) -> Image.Image:
    return Image.new("RGBA", (32, 32), (shade, shade, shade, 128))


def frame_at(time: float) -> Image.Image:
    return frame(int(time * 100) % 256)


def test_flatten_makes_a_translucent_frame_opaque():
    flat = _flatten(frame(200), (0, 0, 0, 0))
    assert flat.getpixel((0, 0))[3] == 255


def test_every_documented_format_has_a_codec():
    assert set(CODECS) == {"prores4444", "animation", "png_mov", "mp4", "png"}


def test_png_sequence_is_numbered_from_the_start_frame(tmp_path):
    render_png_sequence((frame(i) for i in range(3)), tmp_path, start_frame=7)
    assert sorted(p.name for p in tmp_path.glob("*.png")) == [
        "frame_000007.png",
        "frame_000008.png",
        "frame_000009.png",
    ]


def test_png_sequence_keeps_alpha(tmp_path):
    render_png_sequence((frame(200) for _ in range(1)), tmp_path)
    saved = Image.open(next(tmp_path.glob("*.png")))
    assert saved.mode == "RGBA"
    assert saved.getpixel((0, 0))[3] == 128


@needs_ffmpeg
def test_a_prores_file_keeps_its_alpha_channel(tmp_path):
    destination = tmp_path / "out.mov"
    render_frames((frame(i * 20) for i in range(5)), destination, TINY)
    assert destination.exists() and destination.stat().st_size > 0


@needs_ffmpeg
def test_an_mp4_is_flattened_rather_than_refused(tmp_path):
    destination = tmp_path / "out.mp4"
    output = Output(width=32, height=32, fps=10, format="mp4", background=(0, 0, 0, 255))
    render_frames((frame(i * 20) for i in range(5)), destination, output)
    assert destination.exists() and destination.stat().st_size > 0


@needs_ffmpeg
def test_segments_are_concatenated_into_one_file(tmp_path):
    destination = tmp_path / "out.mov"
    seen: list[tuple[int, int]] = []
    render_segmented(
        frame_at, destination, TINY, start=0.0, end=6.0, on_segment=lambda a, b: seen.append((a, b))
    )
    # Six seconds at 1.5-second segments: four parts, joined into one file.
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert destination.exists() and destination.stat().st_size > 0


@needs_ffmpeg
def test_a_short_render_skips_the_segmenting_machinery(tmp_path):
    seen: list[tuple[int, int]] = []
    render_segmented(
        frame_at,
        tmp_path / "out.mov",
        TINY,
        start=0.0,
        end=0.3,
        on_segment=lambda a, b: seen.append((a, b)),
    )
    assert seen == [(1, 1)]


@needs_ffmpeg
def test_a_frame_of_the_wrong_size_is_refused(tmp_path):
    # ffmpeg would accept the bytes — raw video has no framing — and write a
    # torn, diagonally smeared video instead of failing.
    wrong = (Image.new("RGBA", (64, 64)) for _ in range(3))
    with pytest.raises(EncodeError, match="64x64"):
        render_frames(wrong, tmp_path / "out.mov", TINY)


@needs_ffmpeg
@pytest.mark.parametrize("fmt", ["prores4444", "animation", "png_mov"])
def test_every_overlay_format_keeps_its_alpha(tmp_path, fmt):
    """The point of all three is a transparent overlay; a format that flattened
    it would be useless however small it came out."""
    import json
    import subprocess

    output = Output(width=32, height=32, fps=10, format=fmt, background=(0, 0, 0, 0))
    destination = tmp_path / f"out{CODECS[fmt].suffix}"
    render_frames((frame(120) for _ in range(5)), destination, output)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=pix_fmt", "-of", "json", str(destination)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    pixel_format = json.loads(probe.stdout)["streams"][0]["pix_fmt"]
    assert "a" in pixel_format, f"{fmt} came out as {pixel_format}, with no alpha"


@needs_ffmpeg
def test_the_lossless_formats_are_smaller_than_prores(tmp_path):
    # The whole reason they are offered. Flat colour on a transparent field is
    # the worst case for an intra-frame DCT codec.
    sizes = {}
    for fmt in ("prores4444", "animation", "png_mov"):
        output = Output(width=32, height=32, fps=10, format=fmt, background=(0, 0, 0, 0))
        destination = tmp_path / f"{fmt}{CODECS[fmt].suffix}"
        render_frames((frame(120) for _ in range(10)), destination, output)
        sizes[fmt] = destination.stat().st_size
    assert sizes["animation"] < sizes["prores4444"]
    assert sizes["png_mov"] < sizes["prores4444"]


@pytest.fixture
def two_second_clip(tmp_path):
    """A green second then a yellow one, so a loop and a seam are both visible.

    The rate is set on each source rather than on the output: two 25fps sources
    resampled to 10 on the way out come to 2.2 seconds, not 2, and every
    expectation below would then be off by the difference.
    """
    path = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "color=c=green:s=64x64:d=1:r=10",
         "-f", "lavfi", "-i", "color=c=yellow:s=64x64:d=1:r=10",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
         str(path)],
        check=True,
    )  # fmt: skip
    return path


def _colour_at(video: Path, when: float) -> str:
    """green, yellow or something else, sampled from one frame of a video.

    The seek goes after the input, not before it: seeking before decoding jumps
    to the nearest keyframe, which on a flat-colour clip can be a whole second
    away and makes this read the wrong second entirely.
    """
    with TemporaryDirectory() as workdir:
        shot = Path(workdir) / "f.png"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-ss", f"{when}",
             "-frames:v", "1", str(shot)],
            check=True,
        )  # fmt: skip
        with Image.open(shot) as image:
            red, green, blue = image.convert("RGB").getpixel((8, 8))
    if green > 100 and red < 100:
        return "green"
    if red > 100 and green > 100:
        return "yellow"
    return f"({red},{green},{blue})"


@needs_ffmpeg
def test_a_clip_shows_through_the_overlay(tmp_path, two_second_clip):
    # The frames handed to the encoder are see-through; if they were flattened
    # onto the preset's colour first the clip would be hidden completely.
    clear = [Image.new("RGBA", (64, 64), (0, 0, 0, 0)) for _ in range(10)]
    output = Output(width=64, height=64, fps=10, format="mp4")
    result = render_frames(
        iter(clear),
        tmp_path / "over.mp4",
        output,
        background=Background(video=str(two_second_clip)),
    )
    assert _colour_at(result, 0.5) == "green"


@needs_ffmpeg
def test_a_short_clip_repeats_under_a_longer_song(tmp_path, two_second_clip):
    clear = (Image.new("RGBA", (64, 64), (0, 0, 0, 0)) for _ in range(60))
    output = Output(width=64, height=64, fps=10, format="mp4")
    result = render_frames(
        clear,
        tmp_path / "loop.mp4",
        output,
        background=Background(video=str(two_second_clip)),
    )
    # Six seconds of frames over a two-second clip: three times round.
    assert [_colour_at(result, t) for t in (0.5, 1.5, 2.5, 5.5)] == [
        "green", "yellow", "green", "yellow",
    ]


@needs_ffmpeg
def test_the_clip_carries_on_across_a_segment_seam(tmp_path, two_second_clip):
    output = Output(width=64, height=64, fps=10, format="mp4", segment_seconds=1.5)
    result = render_segmented(
        lambda _: Image.new("RGBA", (64, 64), (0, 0, 0, 0)),
        tmp_path / "seams.mp4",
        output,
        start=0.0,
        end=6.0,
        background=Background(video=str(two_second_clip)),
    )
    # Seams at 1.5, 3.0 and 4.5; the clip must not restart at any of them.
    assert [_colour_at(result, t) for t in (1.6, 3.2, 4.6)] == ["yellow", "yellow", "green"]


@needs_ffmpeg
def test_a_clip_that_is_not_there_says_so(tmp_path):
    with pytest.raises(EncodeError, match="is not there"):
        render_frames(
            iter([Image.new("RGBA", (32, 32), (0, 0, 0, 0))]),
            tmp_path / "x.mp4",
            Output(width=32, height=32, fps=10, format="mp4"),
            background=Background(video=str(tmp_path / "missing.mp4")),
        )
