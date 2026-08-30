import re
import time
from pathlib import Path

import pytest

from conftest import make_line, make_song

fastapi = pytest.importorskip("fastapi", reason="needs the web extra")
from fastapi.testclient import TestClient  # noqa: E402

import videokar.web.app  # noqa: E402
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


def test_the_page_carries_no_code_of_its_own(client):
    # The page is markup and nothing else. Kept honest here because inline code
    # is exactly what creeps back in one convenient line at a time.
    page = client.get("/").text
    assert "<script type=\"module\" src=\"/static/js/main.js\">" in page
    assert '<link rel="stylesheet" href="/static/style.css">' in page
    assert "<style>" not in page
    assert re.search(r"<script(?![^>]*\ssrc=)", page) is None


def test_every_route_is_mounted(client):
    # The routers are listed by hand in web/routes/__init__.py, so a new module
    # that nobody adds to ROUTERS would simply not be there. Each of these is a
    # request the page makes. A handler is free to answer 404 — this fixture has
    # no audio on disk — so what is checked is the routing 404, which carries
    # FastAPI's own "Not Found" rather than a message meant for the reader.
    for method, path in [
        ("GET", "/api/song"),
        ("GET", "/api/library"),
        ("HEAD", "/api/library"),
        ("POST", "/api/open"),
        ("POST", "/api/edit"),
        ("POST", "/api/undo"),
        ("GET", "/api/peaks"),
        ("GET", "/api/audio"),
        ("POST", "/api/discard"),
        ("POST", "/api/songs"),
        ("GET", "/api/fonts"),
        ("POST", "/api/fonts"),
        ("POST", "/api/sprites"),
        ("GET", "/api/style"),
        ("POST", "/api/style"),
        ("POST", "/api/render"),
        ("GET", "/api/frame"),
        ("GET", "/api/jobs"),
    ]:
        response = client.request(method, path)
        assert response.status_code != 405, f"{method} {path} refuses that method"
        if response.status_code == 404:
            assert response.json()["detail"] != "Not Found", f"{method} {path} is not mounted"


def test_the_stylesheet_and_every_module_are_served(client):
    static = Path(videokar.web.app.__file__).parent / "static"
    wanted = ["/static/style.css"] + sorted(
        f"/static/js/{f.name}" for f in (static / "js").glob("*.js")
    )
    assert "/static/js/main.js" in wanted
    for path in wanted:
        response = client.get(path)
        assert response.status_code == 200, path
        # A cached script against a restarted server is the same trap as a
        # cached page: it looks like the fix did not take.
        assert response.headers["cache-control"] == "no-store", path


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
    assert job["file"] == "song-1.mov"


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


def test_a_preview_frame_comes_back_as_an_image(client):
    response = client.get("/api/frame", params={"at": 20.5, "width": 200})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_a_preview_frame_is_the_width_asked_for(client):
    import io

    from PIL import Image

    response = client.get("/api/frame", params={"at": 20.5, "width": 200})
    assert Image.open(io.BytesIO(response.content)).size[0] == 200


def test_moving_the_words_changes_the_preview(client):
    low = client.get("/api/frame", params={"at": 20.5, "margin_y": 20}).content
    high = client.get("/api/frame", params={"at": 20.5, "margin_y": 400}).content
    assert low != high


def test_a_preview_with_a_setting_the_schema_refuses_says_so(client):
    response = client.get("/api/frame", params={"at": 20.5, "anchor": "sideways"})
    assert response.status_code == 422
    assert "layout.anchor" in response.json()["detail"]


def test_a_render_takes_any_setting_the_schema_knows(client):
    job = client.post(
        "/api/render",
        json={"preset": "alpha", "overrides": {"layout": {"anchor": "top", "margin_y": 40}}},
    )
    assert job.status_code == 200


def test_a_render_with_a_setting_the_schema_refuses_says_so(client):
    response = client.post(
        "/api/render", json={"overrides": {"layout": {"anchor": "sideways"}}}
    )
    assert response.status_code == 422
    assert "layout.anchor" in response.json()["detail"]


def test_an_override_does_not_lose_the_named_output_fields(client):
    # width/height/fps arrive as their own fields and must survive being merged
    # with whatever else the page sent.
    from videokar.web.models import RenderRequest
    from videokar.web.style import style_for

    style = style_for(
        RenderRequest(preset="alpha", fps=48, overrides={"output": {"width": 640}})
    )
    assert (style.output.fps, style.output.width, style.output.format) == (48, 640, "prores4444")


@pytest.fixture
def a_sprite(tmp_path):
    from PIL import Image

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(16, 48):
        for y in range(16, 48):
            image.putpixel((x, y), (0, 255, 0, 255))
    path = tmp_path / "blob.png"
    image.save(path)
    return path


def test_the_library_lists_the_pngs_it_could_bounce(client, a_sprite):
    assert client.get("/api/library").json()["sprites"] == ["blob.png"]


def test_a_sprite_can_be_uploaded(client, tmp_path):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(buffer, format="PNG")
    response = client.post(
        "/api/sprites", files={"image": ("my ball.png", buffer.getvalue(), "image/png")}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "my-ball.png"
    assert (tmp_path / "my-ball.png").exists()


def test_something_that_is_not_a_png_is_refused(client):
    response = client.post(
        "/api/sprites", files={"image": ("thing.jpg", b"\xff\xd8\xff", "image/jpeg")}
    )
    assert response.status_code == 422
    assert "PNG" in response.json()["detail"]


def test_a_png_that_is_not_an_image_is_refused_and_not_kept(client, tmp_path):
    response = client.post(
        "/api/sprites", files={"image": ("broken.png", b"not a png at all", "image/png")}
    )
    assert response.status_code == 422
    assert not (tmp_path / "broken.png").exists()


def test_the_preview_can_bounce_a_sprite(client, a_sprite):
    circle = client.get("/api/frame", params={"at": 20.5}).content
    blob = client.get("/api/frame", params={"at": 20.5, "sprite": "blob.png"}).content
    assert circle != blob


def test_a_sprite_that_is_not_there_says_so(client):
    response = client.get("/api/frame", params={"at": 20.5, "sprite": "nope.png"})
    assert response.status_code == 404


def test_a_sprite_name_cannot_walk_out_of_the_folder(client):
    response = client.get("/api/frame", params={"at": 20.5, "sprite": "../secret.png"})
    assert response.status_code in (403, 404)


def test_a_render_can_bounce_a_sprite(client, a_sprite):
    response = client.post(
        "/api/render",
        json={"preset": "alpha", "overrides": {"ball": {"sprite": "blob.png"}}},
    )
    assert response.status_code == 200


def test_a_render_with_a_sprite_outside_the_folder_is_refused(client):
    response = client.post(
        "/api/render",
        json={"overrides": {"ball": {"sprite": "/etc/passwd"}}},
    )
    assert response.status_code in (403, 404)


def test_head_on_the_library_is_answered(client):
    # The page polls this to notice a server that has gone away; a 405 with a
    # JSON body would answer, which would make a dead server look alive.
    assert client.head("/api/library").status_code == 200


def test_nothing_live_is_cacheable(client):
    # With no headers at all a browser caches heuristically, and a tab running
    # last week's page looks like the app freezing rather than like a cache.
    for path in ("/", "/api/song", "/api/library"):
        assert client.get(path).headers.get("cache-control") == "no-store", path


def test_a_finished_file_may_be_cached(client, tmp_path):
    (tmp_path / "song.mov").write_bytes(b"not really a movie")
    assert "no-store" not in client.get("/api/output/song.mov").headers.get("cache-control", "")


def test_the_page_says_which_version_it_is(client):
    from videokar import __version__

    body = client.get("/").text
    assert "{{version}}" not in body
    assert __version__ in body


def test_no_settings_saved_yet_is_not_an_error(client):
    payload = client.get("/api/style").json()
    assert payload["saved"] is False
    assert payload["overrides"] == {}


def test_settings_are_remembered_between_visits(client, tmp_path):
    body = {
        "preset": "alpha",
        "overrides": {"layout": {"anchor": "bottom", "margin_y": 540}, "ball": {"squash": 0.3}},
    }
    assert client.post("/api/style", json=body).status_code == 200

    payload = client.get("/api/style").json()
    assert payload["saved"] is True
    assert payload["preset"] == "alpha"
    assert payload["overrides"]["layout"]["margin_y"] == 540
    assert payload["overrides"]["ball"]["squash"] == 0.3


def test_the_settings_land_in_the_file_the_cli_reads(client, tmp_path):
    from videokar.config import resolve_style

    client.post(
        "/api/style",
        json={"preset": "alpha", "overrides": {"layout": {"margin_y": 540}}},
    )
    written = tmp_path / "videokar.toml"
    assert written.exists()
    # The same file `videokar render -c` takes, so the view is reproducible.
    style = resolve_style(written)
    assert style.layout.margin_y == 540
    assert style.output.format == "prores4444"


def test_settings_the_schema_refuses_are_not_written(client, tmp_path):
    response = client.post(
        "/api/style", json={"overrides": {"layout": {"anchor": "sideways"}}}
    )
    assert response.status_code == 422
    assert not (tmp_path / "videokar.toml").exists()


def test_the_fonts_this_machine_offers_are_listed(client):
    fonts = client.get("/api/fonts").json()["fonts"]
    assert fonts
    assert all("path" in font and "label" in font for font in fonts)


def test_a_font_can_be_used_in_the_preview(client):
    fonts = client.get("/api/fonts").json()["fonts"]
    plain = client.get("/api/frame", params={"at": 20.5}).content
    styled = client.get("/api/frame", params={"at": 20.5, "font": fonts[0]["path"]}).content
    assert plain != styled


def test_a_font_this_machine_does_not_offer_is_refused(client):
    # A path from a page is not a reason to read an arbitrary file off the disk.
    response = client.get("/api/frame", params={"at": 20.5, "font": "/etc/passwd"})
    assert response.status_code == 404
    assert "not a font this machine offers" in response.json()["detail"]


def test_a_render_with_an_unoffered_font_is_refused(client):
    response = client.post(
        "/api/render", json={"overrides": {"main": {"font": "/etc/passwd"}}}
    )
    assert response.status_code == 404


def test_the_main_text_size_reaches_the_preview(client):
    small = client.get("/api/frame", params={"at": 20.5, "font_size": 40}).content
    large = client.get("/api/frame", params={"at": 20.5, "font_size": 120}).content
    assert small != large


def test_uploading_something_that_is_not_a_font_is_refused(client, tmp_path):
    response = client.post(
        "/api/fonts", files={"font": ("notes.ttf", b"not a font", "font/ttf")}
    )
    assert response.status_code == 422
    assert not (tmp_path / "notes.ttf").exists()


def test_uploading_a_file_with_the_wrong_suffix_is_refused(client):
    response = client.post("/api/fonts", files={"font": ("thing.doc", b"x", "text/plain")})
    assert response.status_code == 422
    assert ".ttf" in response.json()["detail"]


def test_the_size_and_font_are_remembered(client, tmp_path):
    fonts = client.get("/api/fonts").json()["fonts"]
    client.post(
        "/api/style",
        json={"preset": "alpha", "overrides": {"main": {"size": 96, "font": fonts[0]["path"]}}},
    )
    from videokar.config import resolve_style

    style = resolve_style(tmp_path / "videokar.toml")
    assert style.main.size == 96
    assert style.main.font == fonts[0]["path"]


def test_each_export_gets_its_own_name(client, tmp_path):
    first = client.post("/api/render", json={"preset": "alpha"}).json()
    second = client.post("/api/render", json={"preset": "alpha"}).json()
    # Overwriting one name made a file downloaded earlier indistinguishable from
    # the one just made, which looks like the new one drifting.
    assert first["file"] != second["file"]
    assert first["file"] == "song-1.mov"
    assert second["file"] == "song-2.mov"


def test_the_numbering_skips_names_already_taken(client, tmp_path):
    (tmp_path / "song-1.mov").write_bytes(b"an earlier export")
    job = client.post("/api/render", json={"preset": "alpha"}).json()
    assert job["file"] == "song-2.mov"
    assert (tmp_path / "song-1.mov").read_bytes() == b"an earlier export"


@pytest.mark.parametrize("name", ["song.m4a", "song.flac", "song.opus", "song.aac", "song.wav"])
def test_the_usual_audio_files_are_accepted(client, name):
    # The suffix check is a guard against an obvious mistake; ffprobe decides
    # what can actually be read, and says so clearly when it cannot.
    response = client.post(
        "/api/songs",
        files={"audio": (name, b"\x00" * 32, "audio/mpeg")},
        data={"lyrics": "[Verse 1]\nhello there"},
    )
    assert response.status_code == 200


def test_a_song_is_moved_to_trash_not_deleted(client, tmp_path):
    response = client.post("/api/discard", json={"path": str(tmp_path / "song.json")})
    assert response.status_code == 200
    assert not (tmp_path / "song.json").exists()
    # Somebody's work, one click, and a mistake costs an alignment run.
    assert (tmp_path / ".trash" / "song.json").exists()


def test_discarding_the_open_song_leaves_nothing_open(client, tmp_path):
    client.post("/api/discard", json={"path": str(tmp_path / "song.json")})
    assert client.get("/api/song").status_code == 409


def test_a_song_outside_the_folder_cannot_be_discarded(client, tmp_path):
    assert client.post(
        "/api/discard", json={"path": str(tmp_path.parent / "elsewhere.json")}
    ).status_code == 403


def test_discarding_twice_keeps_both_copies(client, tmp_path):
    from conftest import make_line, make_song
    from videokar.project import save_song

    client.post("/api/discard", json={"path": str(tmp_path / "song.json")})
    save_song(make_song(make_line("l0", ["x"], 1.0)), tmp_path / "song.json")
    client.post("/api/discard", json={"path": str(tmp_path / "song.json")})
    assert (tmp_path / ".trash" / "song.json").exists()
    assert (tmp_path / ".trash" / "song-1.json").exists()


def test_the_audio_is_left_alone_unless_asked_for(client, tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"audio")
    client.post("/api/discard", json={"path": str(tmp_path / "song.json")})
    assert (tmp_path / "a.mp3").exists()


def test_retyping_a_line_through_the_api(client):
    response = client.post(
        "/api/edit", json={"op": "set_line_text", "line": "l1", "text": "d e f g"}
    )
    assert response.status_code == 200
    assert load_song(client.song_path).line("l1").words_text == "d e f g"


def test_the_preview_takes_the_same_overrides_as_a_render(client):
    import json

    plain = client.get("/api/frame", params={"at": 20.5}).content
    styled = client.get(
        "/api/frame",
        params={
            "at": 20.5,
            "extra": json.dumps(
                {"main": {"colour_on": "#ff0000"}, "shadow": {"colour": "#000000c8"}}
            ),
        },
    ).content
    assert plain != styled


def test_a_preview_override_that_is_not_json_says_so(client):
    response = client.get("/api/frame", params={"at": 20.5, "extra": "{nope"})
    assert response.status_code == 422
    assert "not JSON" in response.json()["detail"]


def test_a_preview_override_the_schema_refuses_says_so(client):
    import json

    response = client.get(
        "/api/frame",
        params={"at": 20.5, "extra": json.dumps({"main": {"colour_on": "burnt sienna"}})},
    )
    assert response.status_code == 422


def test_the_colours_and_the_shadow_are_remembered(client, tmp_path):
    from videokar.config import resolve_style

    client.post(
        "/api/style",
        json={
            "preset": "alpha",
            "overrides": {
                "main": {"colour_on": "#9be7c4", "outline": "#000000d2", "outline_width": 5},
                "shadow": {"colour": "#000000c8"},
            },
        },
    )
    style = resolve_style(tmp_path / "videokar.toml")
    assert style.main.colour_on == (155, 231, 196, 255)
    assert style.main.outline_width == 5
    assert style.shadow.colour == (0, 0, 0, 200)


def test_a_named_parameter_does_not_drop_the_ball_extras(client):
    # squash arrives as its own parameter and the colour through `extra`; the
    # one must not assign over the section the other landed in.
    import json

    from videokar.render import FrameRenderer

    seen = {}
    original = FrameRenderer.__init__

    def spy(self, song, style):
        seen["ball"] = style.ball
        original(self, song, style)

    FrameRenderer.__init__ = spy
    try:
        response = client.get(
            "/api/frame",
            params={
                "at": 20.5,
                "squash": 0.3,
                "extra": json.dumps({"ball": {"colour": "#00ff00", "radius": 42}}),
            },
        )
    finally:
        FrameRenderer.__init__ = original
    assert response.status_code == 200
    assert seen["ball"].squash == 0.3
    assert seen["ball"].colour == (0, 255, 0, 255)
    assert seen["ball"].radius == 42


def test_the_circle_can_be_asked_for_after_a_sprite(client, tmp_path):
    # Overrides merge per key, so a ball section that only stops naming a sprite
    # leaves the saved one in place. Saying "ball" is what clears it.
    from videokar.config import resolve_style
    from videokar.web.models import RenderRequest
    from videokar.web.style import style_for

    client.post(
        "/api/style",
        json={"preset": "alpha", "overrides": {"ball": {"kind": "sprite", "sprite": "cat.png"}}},
    )
    saved = resolve_style(tmp_path / "videokar.toml")
    assert saved.ball.kind == "sprite"

    client.post(
        "/api/style",
        json={"preset": "alpha", "overrides": {"ball": {"kind": "ball", "colour": "#ff0000"}}},
    )
    now = resolve_style(tmp_path / "videokar.toml")
    assert now.ball.kind == "ball"
    assert now.ball.colour == (255, 0, 0, 255)

    style = style_for(RenderRequest(preset="alpha", overrides={"ball": {"kind": "ball"}}))
    assert style.ball.kind == "ball"
