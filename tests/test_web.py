import time

import pytest

from conftest import make_line, make_song

fastapi = pytest.importorskip("fastapi", reason="needs the web extra")
from fastapi.testclient import TestClient  # noqa: E402

from videokar.project import load_song, save_song  # noqa: E402
from videokar.web import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    song = make_song(
        make_line("l0", ["a", "b", "c"], 10.0),
        make_line("l1", ["d", "e", "f"], 20.0),
        make_line("l2", ["g", "h", "i"], 30.0),
    )
    path = save_song(song, tmp_path / "song.json")
    app = create_app(path)
    client = TestClient(app)
    client.song_path = path
    return client


def test_the_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "videokar" in response.text


def test_the_document_comes_back_with_fresh_flags(client):
    payload = client.get("/api/song").json()
    assert [s["id"] for s in payload["song"]["sections"]] == ["s0"]
    assert payload["suspicious"] == []
    assert payload["issues"] == []


def test_an_edit_is_applied_and_written_to_disk(client):
    response = client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": 2.0})
    assert response.status_code == 200
    assert load_song(client.song_path).line("l1").start == pytest.approx(22.0)


def test_an_edit_ripples_into_the_response(client):
    payload = client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": 2.0}).json()
    assert payload["edit"]["moved"] == ["l1", "l2"]


def test_a_pin_stops_the_ripple_through_the_api(client):
    client.post("/api/edit", json={"op": "pin", "line": "l2", "value": True})
    client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": 2.0})
    song = load_song(client.song_path)
    assert song.line("l2").start == pytest.approx(30.0)
    assert song.line("l2").pinned


def test_a_refused_drag_comes_back_as_a_message_not_a_crash(client):
    response = client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": -10.0})
    assert response.status_code == 409
    assert "before l0 ends" in response.json()["detail"]
    # And the file is untouched.
    assert load_song(client.song_path).line("l1").start == pytest.approx(20.0)


def test_an_unknown_line_is_refused_with_a_reason(client):
    response = client.post("/api/edit", json={"op": "shift_line", "line": "l99", "by": 1.0})
    assert response.status_code == 409
    assert "l99" in response.json()["detail"]


def test_retyping_a_word_updates_the_aligner_form_too(client):
    client.post("/api/edit", json={"op": "set_text", "word": "l1.w0", "text": "purrs"})
    song = load_song(client.song_path)
    assert song.word("l1.w0").text == "purrs"
    assert song.word("l1.w0").norm == "purrs"
    assert song.word("l1.w0").manual
    # The line's readable copy follows, so check has nothing to complain about.
    assert song.line("l1").text == "purrs e f"
    assert client.get("/api/song").json()["issues"] == []


def test_a_word_cannot_be_retyped_into_two(client):
    response = client.post(
        "/api/edit", json={"op": "set_text", "word": "l1.w0", "text": "two words"}
    )
    assert response.status_code == 409
    assert "one token" in response.json()["detail"]


def test_muting_a_line_through_the_api(client):
    client.post("/api/edit", json={"op": "mute", "line": "l1", "value": False})
    assert not load_song(client.song_path).line("l1").sung


def test_moving_one_word(client):
    client.post("/api/edit", json={"op": "move_word", "word": "l1.w1", "to": 20.52})
    assert load_song(client.song_path).word("l1.w1").start == pytest.approx(20.52)


def test_an_unknown_operation_is_refused(client):
    assert client.post("/api/edit", json={"op": "explode"}).status_code == 409


def test_peaks_and_audio_say_so_when_there_is_no_audio(client):
    assert client.get("/api/peaks").status_code == 404
    assert client.get("/api/audio").status_code == 404


def test_undo_steps_back_through_edits(client):
    client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": 2.0})
    client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": 1.0})
    assert load_song(client.song_path).line("l1").start == pytest.approx(23.0)

    client.post("/api/undo")
    assert load_song(client.song_path).line("l1").start == pytest.approx(22.0)
    client.post("/api/undo")
    assert load_song(client.song_path).line("l1").start == pytest.approx(20.0)


def test_undo_with_nothing_to_undo_says_so(client):
    response = client.post("/api/undo")
    assert response.status_code == 409
    assert "nothing to undo" in response.json()["detail"]


def test_a_refused_edit_does_not_land_on_the_undo_stack(client):
    client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": -10.0})
    assert client.post("/api/undo").status_code == 409


def test_undo_restores_a_retyped_word(client):
    client.post("/api/edit", json={"op": "set_text", "word": "l1.w0", "text": "purrs"})
    client.post("/api/undo")
    assert load_song(client.song_path).word("l1.w0").text == "d"


def test_dragging_a_word_edge_changes_how_long_it_lasts(client):
    # l1.w0 is 20.00-20.45 and l1.w1 starts at 20.50, so 20.48 is the room there is.
    client.post("/api/edit", json={"op": "resize_word", "word": "l1.w0", "end": 20.48})
    word = load_song(client.song_path).word("l1.w0")
    assert word.end == pytest.approx(20.48)
    assert word.start == pytest.approx(20.0)


def test_dragging_the_left_edge_moves_only_the_onset(client):
    client.post("/api/edit", json={"op": "resize_word", "word": "l1.w1", "start": 20.46})
    word = load_song(client.song_path).word("l1.w1")
    assert word.start == pytest.approx(20.46)
    assert word.end == pytest.approx(20.95)


def test_a_word_cannot_be_resized_over_its_neighbour(client):
    response = client.post("/api/edit", json={"op": "resize_word", "word": "l1.w0", "end": 21.4})
    assert response.status_code == 409
    assert "l1.w1" in response.json()["detail"]


def test_a_word_cannot_be_resized_into_the_next_line(client):
    # l1's last word ends at 21.45 and l2 starts at 30.0.
    response = client.post("/api/edit", json={"op": "resize_word", "word": "l1.w2", "end": 31.0})
    assert response.status_code == 409
    assert "l2" in response.json()["detail"]


def test_a_word_cannot_be_squeezed_to_nothing(client):
    response = client.post("/api/edit", json={"op": "resize_word", "word": "l1.w0", "end": 20.01})
    assert response.status_code == 409
    assert "grab it again" in response.json()["detail"]


def test_resizing_a_word_moves_the_line_edge_with_it(client):
    client.post("/api/edit", json={"op": "resize_word", "word": "l1.w2", "end": 22.5})
    assert load_song(client.song_path).line("l1").end == pytest.approx(22.5)


def test_the_library_lists_documents_and_presets(client, tmp_path):
    payload = client.get("/api/library").json()
    assert payload["workdir"] == str(tmp_path)
    assert [song["name"] for song in payload["songs"]] == ["song.json"]
    assert "alpha" in payload["presets"]


def test_the_library_skips_json_that_is_not_ours(client, tmp_path):
    (tmp_path / "other.json").write_text('{"unrelated": true}')
    (tmp_path / "list.json").write_text("[1, 2, 3]")
    assert [s["name"] for s in client.get("/api/library").json()["songs"]] == ["song.json"]


def test_opening_another_document_switches_the_view(client, tmp_path):
    from conftest import make_line, make_song
    from videokar.project import save_song

    other = save_song(make_song(make_line("l0", ["x", "y"], 5.0)), tmp_path / "other.json")
    payload = client.post("/api/open", json={"path": str(other)}).json()
    assert payload["path"] == str(other)
    assert client.get("/api/song").json()["path"] == str(other)


def test_opening_something_outside_the_folder_is_refused(client, tmp_path):
    outside = tmp_path.parent / "elsewhere.json"
    response = client.post("/api/open", json={"path": str(outside)})
    assert response.status_code == 403


def test_opening_a_file_that_will_not_load_is_refused(client, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{nope")
    assert client.post("/api/open", json={"path": str(broken)}).status_code == 409


def test_undo_history_does_not_leak_across_documents(client, tmp_path):
    from conftest import make_line, make_song
    from videokar.project import save_song

    client.post("/api/edit", json={"op": "shift_line", "line": "l1", "by": 1.0})
    other = save_song(make_song(make_line("l0", ["x", "y"], 5.0)), tmp_path / "other.json")
    client.post("/api/open", json={"path": str(other)})
    # Undoing here must not reach back into the document that was open before.
    assert client.post("/api/undo").status_code == 409


def test_a_render_needs_a_format_it_can_hand_back(client):
    response = client.post("/api/render", json={"format": "png"})
    assert response.status_code == 422
    assert "PNG sequence" in response.json()["detail"]


def test_an_unknown_preset_is_refused(client):
    assert client.post("/api/render", json={"preset": "nope"}).status_code == 422


def test_uploading_something_that_is_not_audio_is_refused(client):
    response = client.post(
        "/api/songs",
        files={"audio": ("notes.txt", b"hello", "text/plain")},
        data={"lyrics": "hello there"},
    )
    assert response.status_code == 422
    assert "audio file" in response.json()["detail"]


def test_uploading_without_lyrics_is_refused(client):
    response = client.post(
        "/api/songs",
        files={"audio": ("song.mp3", b"\x00" * 32, "audio/mpeg")},
        data={"lyrics": "   "},
    )
    assert response.status_code == 422


def test_an_upload_starts_a_job_and_keeps_the_file(client, tmp_path):
    response = client.post(
        "/api/songs",
        files={"audio": ("my song.mp3", b"\x00" * 32, "audio/mpeg")},
        data={"lyrics": "[Verse 1]\nhello there"},
    )
    assert response.status_code == 200
    job = response.json()
    assert job["kind"] == "align"
    # The name is sanitised: nothing user-supplied escapes the folder.
    assert (tmp_path / "my-song.mp3").exists()
    assert job["document"].endswith("my-song.json")


def test_a_rendered_file_is_served_by_name(client, tmp_path):
    (tmp_path / "song.mov").write_bytes(b"not really a movie")
    response = client.get("/api/output/song.mov")
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('filename="song.mov"')


def test_head_on_an_output_is_answered_rather_than_refused(client, tmp_path):
    # A 405 carries a JSON body, and <a download> would save that as the video.
    (tmp_path / "song.mov").write_bytes(b"not really a movie")
    assert client.head("/api/output/song.mov").status_code == 200


def test_an_output_that_is_gone_says_so(client):
    response = client.get("/api/output/song.mov")
    assert response.status_code == 404
    assert "not there any more" in response.json()["detail"]


def test_an_output_name_cannot_walk_out_of_the_folder(client):
    assert client.get("/api/output/..%2F..%2Fetc%2Fpasswd").status_code in (403, 404)
    assert client.get("/api/output/sub%2Fthing.mov").status_code in (403, 404)


def test_a_render_job_names_the_file_it_will_produce(client):
    job = client.post("/api/render", json={"preset": "alpha"}).json()
    assert job["file"] == "song.mov"


def test_a_job_that_fails_reports_why_rather_than_crashing(client, tmp_path):
    # Thirty-two zero bytes is not an mp3, so ffprobe will refuse it.
    job = client.post(
        "/api/songs",
        files={"audio": ("bad.mp3", b"\x00" * 32, "audio/mpeg")},
        data={"lyrics": "[Verse 1]\nhello there"},
    ).json()
    for _ in range(200):
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state["status"] != "running":
            break
        time.sleep(0.05)
    assert state["status"] == "failed"
    assert state["error"]


def test_an_unknown_job_is_a_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
