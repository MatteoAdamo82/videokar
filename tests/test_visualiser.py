import pytest

from videokar.config import Output, Style, Visualiser
from videokar.render.visualiser import filter_chain, placement

OUTPUT = Output(width=1920, height=1080)


def test_it_is_off_unless_asked_for():
    assert Style().visualiser.kind == "none"
    assert filter_chain(Visualiser(), OUTPUT) is None


@pytest.mark.parametrize("kind", ["freqs", "waves", "volume"])
def test_every_kind_produces_a_chain(kind):
    chain = filter_chain(Visualiser(kind=kind), OUTPUT)
    assert chain and chain.endswith("[out]")


def test_the_band_is_drawn_under_the_words_not_over_them():
    # The obvious chain overlays the analysis onto the karaoke frames, which
    # puts a spectrum on top of the lyrics.
    chain = filter_chain(Visualiser(kind="freqs"), OUTPUT)
    assert "[viz][0:v]overlay" in chain
    assert "[0:v][viz]overlay" not in chain


def test_it_reads_the_audio_not_the_video():
    assert filter_chain(Visualiser(kind="freqs"), OUTPUT).startswith("[1:a]")


def test_the_band_is_padded_onto_a_transparent_canvas():
    # Which is what positions it and lets the words sit on top.
    chain = filter_chain(Visualiser(kind="freqs"), OUTPUT)
    assert "pad=1920:1080" in chain
    assert "color=0x00000000" in chain


def test_size_and_position_follow_the_frame():
    width, height, x, y = placement(Visualiser(width=0.5, height=0.2), OUTPUT)
    assert (width, height) == (960, 216)
    assert x == (1920 - 960) // 2
    # Bottom anchored, so it sits near the foot of the frame.
    assert y > OUTPUT.height * 0.7


@pytest.mark.parametrize(
    ("anchor", "check"),
    [
        ("top", lambda y: y < 200),
        ("center", lambda y: 400 < y < 500),
        ("bottom", lambda y: y > 800),
    ],
)
def test_the_anchor_moves_it(anchor, check):
    _, _, _, y = placement(Visualiser(anchor=anchor), OUTPUT)
    assert check(y)


def test_the_colour_reaches_the_filter():
    chain = filter_chain(Visualiser(kind="freqs", colour=(255, 0, 0, 255)), OUTPUT)
    assert "#ff0000" in chain


def test_opacity_is_applied_so_it_sits_behind_the_words():
    chain = filter_chain(Visualiser(kind="freqs", opacity=0.4), OUTPUT)
    assert "colorchannelmixer=aa=0.400" in chain


def test_a_visualiser_without_audio_is_refused():
    from videokar.render.encode import EncodeError, render_frames

    with pytest.raises(EncodeError, match="needs the audio"):
        render_frames(iter([]), "unused.mov", OUTPUT, visualiser="[1:a]anull[out]")


def test_the_output_ends_with_the_frames_not_with_the_song():
    # The base of the overlay is the analysis, which runs to the end of the
    # audio, while the frames handed in are one segment long. Without this the
    # segment lasted as long as the whole song and overlay repeated the last
    # frame it was given — the words froze on whichever line the segment ended
    # on and stayed there for the rest of the video.
    assert "shortest=1" in filter_chain(Visualiser(kind="freqs"), OUTPUT)


# Every kind is run through ffmpeg, not merely built as a string. The string
# tests above passed for months on a `volume` filter ffmpeg refuses outright:
# its colour option is an expression, and a colour is not a valid one.
needs_ffmpeg = pytest.mark.skipif(
    __import__("shutil").which("ffmpeg") is None, reason="ffmpeg is not on PATH"
)


@needs_ffmpeg
@pytest.mark.parametrize("kind", ["freqs", "waves", "volume"])
@pytest.mark.parametrize("colour", [(255, 255, 255, 255), (255, 120, 70, 255)])
def test_ffmpeg_accepts_the_chain(tmp_path, kind, colour):
    import subprocess

    output = Output(width=320, height=180, fps=10)
    chain = filter_chain(Visualiser(kind=kind, colour=colour), output)
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black@0.0:s=320x180:r=10,format=rgba",
            "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-filter_complex", chain, "-map", "[out]", "-frames:v", "10",
            "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
            str(tmp_path / f"{kind}.mov"),
        ],
        capture_output=True, text=True,
    )  # fmt: skip
    assert result.returncode == 0, f"{kind}: {result.stderr.strip()}"
    assert (tmp_path / f"{kind}.mov").stat().st_size > 0
