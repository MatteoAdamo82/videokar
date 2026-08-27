from pathlib import Path

import pytest

from videokar.project import AlignInfo, AudioRef, Line, Section, Song, Word

REPO_ROOT = Path(__file__).resolve().parents[1]
LADYCAT_DIR = REPO_ROOT / "examples" / "ladycat"


@pytest.fixture(scope="session")
def ladycat_lyrics_path() -> Path:
    return LADYCAT_DIR / "lyrics.txt"


@pytest.fixture(scope="session")
def ladycat_audio_path() -> Path:
    path = LADYCAT_DIR / "ladycat.mp3"
    if not path.exists():
        pytest.skip("examples/ladycat/ladycat.mp3 is not present (not distributed with the repo)")
    return path


def word(line_id, position, text, start, end, *, score=0.3, norm=None):
    return Word(
        id=f"{line_id}.w{position}",
        text=text,
        norm=text.lower() if norm is None else norm,
        start=start,
        end=end,
        score=score,
    )


def make_line(line_id, texts, start, step=0.5, **kwargs):
    words = [
        word(line_id, i, t, round(start + i * step, 3), round(start + (i + 1) * step - 0.05, 3))
        for i, t in enumerate(texts)
    ]
    return Line(id=line_id, text=" ".join(texts), words=words, **kwargs)


def make_song(*lines, regions=((0.0, 60.0),)):
    song = Song(
        audio=AudioRef(path="a.mp3", sha256="0" * 64, duration=60.0, sample_rate=44100, channels=2),
        align=AlignInfo(model="MMS_FA", device="cpu"),
        vocal_regions=[tuple(r) for r in regions],
        sections=[Section(id="s0", tag="Verse 1", lines=list(lines))],
    )
    song.refresh_bounds()
    return song


