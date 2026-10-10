"""Testes sem rede; usam substituto do yt-dlp para validar os fluxos HTTP.
Executar: pip install pytest httpx && pytest -q
"""
import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

VIDEO_ID = "dQw4w9WgXcQ"


class FakeYoutubeDL:
    def __init__(self, options=None):
        self.options = options or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def extract_info(self, url, download=False):
        assert VIDEO_ID in url
        return {
            "id": VIDEO_ID,
            "title": "Meu vídeo: teste?!",
            "uploader": "Meu canal",
            "duration": 187,
            "formats": [
                {"height": None, "vcodec": "none", "acodec": "opus"},
                {"height": 360, "vcodec": "avc1", "acodec": "none"},
                {"height": 720, "vcodec": "avc1", "acodec": "none"},
                {"height": 1080, "vcodec": "avc1", "acodec": "none"},
            ],
        }

    def download(self, urls):
        assert urls == [f"https://www.youtube.com/watch?v={VIDEO_ID}"]
        target = Path(self.options["outtmpl"]).parent
        target.mkdir(parents=True, exist_ok=True)
        ext = "mp3" if self.options.get("format") == "bestaudio/best" else "mp4"
        (target / f"{VIDEO_ID}.{ext}").write_bytes(b"conteudo de teste")
        for callback in self.options.get("progress_hooks", []):
            callback({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            callback({"status": "finished"})
        return 0


@pytest.fixture(scope="module")
def server():
    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = FakeYoutubeDL
    sys.modules["yt_dlp"] = module
    spec = importlib.util.spec_from_file_location("clipflow_server_test", Path(__file__).parents[1] / "server.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def api(server, monkeypatch, tmp_path):
    server.video_cache.clear()
    server.jobs.clear()
    monkeypatch.setattr(server, "DOWNLOAD_DIR", tmp_path)
    monkeypatch.setattr(server.shutil, "which", lambda executable: "/usr/bin/fake" if executable in {"ffmpeg", "ffprobe", "deno"} else None)
    return TestClient(server.app)


@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={VIDEO_ID}",
    f"https://youtu.be/{VIDEO_ID}?si=x",
    f"https://www.youtube.com/shorts/{VIDEO_ID}",
    f"https://www.youtube.com/live/{VIDEO_ID}",
    f"https://music.youtube.com/watch?v={VIDEO_ID}",
])
def test_valid_links(server, url):
    actual, normalized = server.normalize_youtube_url(url)
    assert actual == VIDEO_ID
    assert normalized == f"https://www.youtube.com/watch?v={VIDEO_ID}"


@pytest.mark.parametrize("url", [
    "https://youtube.com.attacker.example/watch?v=dQw4w9WgXcQ",
    "http://localhost/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/playlist?list=PL123",
    "https://www.youtube.com/watch?v=invalid",
    "javascript:alert(1)",
    "https://www.youtube.com.evil.org/watch?v=dQw4w9WgXcQ",
])
def test_invalid_links(server, url):
    with pytest.raises(ValueError):
        server.normalize_youtube_url(url)


def test_home_and_health(api):
    home = api.get("/")
    assert home.status_code == 200
    assert "ClipFlow" in home.text
    assert api.get("/api/health").json() == {"ok": True, "ffmpeg": True, "deno": True}


def test_invalid_analyze(api):
    response = api.post("/api/info", json={"url": "https://malicioso.com/x"})
    assert response.status_code == 400


def test_analyze_mp3_download(api):
    response = api.post("/api/info", json={"url": f"https://youtu.be/{VIDEO_ID}"})
    assert response.status_code == 200, response.text
    info = response.json()
    assert info["video_qualities"] == [1080, 720, 360]
    assert info["audio_qualities"] == [128, 192, 256, 320]
    assert info["title"] == "Meu vídeo: teste?!"

    bad = api.post("/api/jobs", json={"video_id": VIDEO_ID, "mode": "mp4", "quality": 2160})
    assert bad.status_code == 400

    job_resp = api.post("/api/jobs", json={"video_id": VIDEO_ID, "mode": "mp3", "quality": 192})
    assert job_resp.status_code == 200, job_resp.text
    job_id = job_resp.json()["job_id"]
    for _ in range(80):
        status = api.get(f"/api/jobs/{job_id}").json()
        if status["status"] == "ready":
            break
        time.sleep(.02)
    assert status["status"] == "ready", status
    finished = api.get(f"/api/files/{job_id}")
    assert finished.status_code == 200
    assert finished.content == b"conteudo de teste"
    assert ".mp3" in finished.headers["content-disposition"]
    assert api.get(f"/api/jobs/{job_id}").status_code == 404


def test_download_mp4(api):
    api.post("/api/info", json={"url": f"https://youtu.be/{VIDEO_ID}"})
    job = api.post("/api/jobs", json={"video_id": VIDEO_ID, "mode": "mp4", "quality": 720}).json()
    for _ in range(80):
        info = api.get(f"/api/jobs/{job['job_id']}").json()
        if info["status"] == "ready":
            break
        time.sleep(.02)
    assert info["status"] == "ready", info
    assert api.get(f"/api/files/{job['job_id']}").content == b"conteudo de teste"
