from videokar.cache import AudioCache, cache_root, clear_cache, file_digest


def test_cache_root_honours_the_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOKAR_CACHE_DIR", str(tmp_path / "cache"))
    assert cache_root() == tmp_path / "cache"


def test_entries_are_keyed_by_content_not_by_name(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOKAR_CACHE_DIR", str(tmp_path / "cache"))
    first, second = tmp_path / "a.wav", tmp_path / "renamed.wav"
    first.write_bytes(b"same audio")
    second.write_bytes(b"same audio")
    # Renaming or moving the track must not cost another separation run.
    assert AudioCache.for_audio(first).directory == AudioCache.for_audio(second).directory


def test_different_content_gets_a_different_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOKAR_CACHE_DIR", str(tmp_path / "cache"))
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    assert AudioCache.for_audio(first).digest != AudioCache.for_audio(second).digest


def test_has_is_false_for_a_truncated_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOKAR_CACHE_DIR", str(tmp_path / "cache"))
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"content")
    cache = AudioCache.for_audio(audio)
    entry = cache.path("vocals.wav")
    entry.touch()
    # A zero-byte file is an interrupted run, not a cache hit.
    assert not cache.has("vocals.wav")
    entry.write_bytes(b"x")
    assert cache.has("vocals.wav")


def test_clear_reports_what_it_reclaimed(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOKAR_CACHE_DIR", str(tmp_path / "cache"))
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"content")
    AudioCache.for_audio(audio).path("vocals.wav").write_bytes(b"x" * 128)
    assert clear_cache() == 128
    assert clear_cache() == 0


def test_file_digest_matches_hashlib(tmp_path):
    import hashlib

    path = tmp_path / "a.bin"
    payload = b"videokar" * 1000
    path.write_bytes(payload)
    assert file_digest(path) == hashlib.sha256(payload).hexdigest()
