from pathlib import Path

import pytest

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
