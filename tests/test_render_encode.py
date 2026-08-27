import pytest
from PIL import Image

from videokar.render.encode import (
    CODECS,
    EncodeError,
    _flatten,
    have_ffmpeg,
    render_frames,
    render_png_sequence,
    render_segmented,
)
from videokar.render.style import Output

needs_ffmpeg = pytest.mark.skipif(not have_ffmpeg(), reason="ffmpeg is not on PATH")

TINY = Output(width=32, height=32, fps=10, segment_seconds=0.5)


def frame(shade: int) -> Image.Image:
    return Image.new("RGBA", (32, 32), (shade, shade, shade, 128))


def frame_at(time: float) -> Image.Image:
    return frame(int(time * 100) % 256)


def test_flatten_makes_a_translucent_frame_opaque():
    flat = _flatten(frame(200), (0, 0, 0, 0))
    assert flat.getpixel((0, 0))[3] == 255


def test_every_documented_format_has_a_codec():
    assert set(CODECS) == {"prores4444", "mp4", "png"}


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
        frame_at, destination, TINY, start=0.0, end=2.0, on_segment=lambda a, b: seen.append((a, b))
    )
    # Two seconds at half-second segments: four parts, joined into one file.
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
