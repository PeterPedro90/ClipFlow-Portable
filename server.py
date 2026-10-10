"""ClipFlow: servidor local para baixar vídeos autorizados do YouTube.

Requer Python 3.11+, FFmpeg, Deno e as dependências de requirements.txt.
Executar: uvicorn server:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from yt_dlp import YoutubeDL

BASE_DIR = Path(__file__).resolve().parent
# No modo portátil os arquivos incorporados são descompactados pelo PyInstaller
# em uma pasta de recursos. Os downloads ficam em uma pasta gravável do usuário.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
STATIC_DIR = RESOURCE_DIR / "static"
if getattr(sys, "frozen", False):
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "ClipFlow"
else:
    DATA_DIR = BASE_DIR
DOWNLOAD_DIR = DATA_DIR / "downloads_temp"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
SAFE_FILENAME_RE = re.compile(r"[^\w\s\-().]", flags=re.UNICODE)
AUDIO_QUALITIES = [128, 192, 256, 320]
CACHE_TTL = 30 * 60
JOB_TTL = 60 * 60
MAX_CONCURRENT_JOBS = 2
MAX_DURATION_SECONDS = 4 * 60 * 60  # limite conservador para uso local
MAX_FILESIZE = 2 * 1024 * 1024 * 1024

app = FastAPI(title="ClipFlow", version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

cache_lock = threading.Lock()
job_lock = threading.Lock()
video_cache: dict[str, dict] = {}
jobs: dict[str, dict] = {}
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class DownloadRequest(BaseModel):
    video_id: str
    mode: str
    quality: int


def normalize_youtube_url(value: str) -> tuple[str, str]:
    """Aceita apenas IDs válidos, reconstroi URL segura do YouTube."""
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password or parsed.port:
        raise ValueError("Cole uma URL completa e válida do YouTube.")
    host = (parsed.hostname or "").lower().rstrip(".")
    parts = [piece for piece in parsed.path.split("/") if piece]

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parts[0] if len(parts) == 1 else ""
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
            video_id = parts[1]
        else:
            video_id = ""
    else:
        video_id = ""

    if not ID_RE.fullmatch(video_id):
        raise ValueError("Este link não corresponde a um vídeo válido do YouTube.")
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


def get_ydl_options() -> dict:
    return {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "skip_unavailable_fragments": False,
        "ignoreerrors": False,
        "restrictfilenames": True,
    }


def available_heights(info: dict) -> list[int]:
    heights: set[int] = set()
    for fmt in info.get("formats") or []:
        height = fmt.get("height")
        if fmt.get("vcodec") in {None, "none"}:
            continue
        if isinstance(height, int) and 144 <= height <= 4320:
            heights.add(height)
    return sorted(heights, reverse=True)


def friendly_error(exc: Exception) -> str:
    message = str(exc).replace("ERROR: ", "").strip()
    if any(s in message.lower() for s in ["sign in", "private video", "not available", "unavailable"]):
        return "O vídeo está indisponível, privado ou exige acesso que este site não possui."
    if "ffmpeg" in message.lower():
        return "Não foi possível converter. Verifique se o FFmpeg está incluído no aplicativo."
    return (message[:220] or "Não foi possível processar o vídeo. Tente novamente.")


def cleanup_expired() -> None:
    now = time.time()
    with cache_lock:
        for key, value in list(video_cache.items()):
            if now - value["created"] > CACHE_TTL:
                video_cache.pop(key, None)
    expired_dirs: list[Path] = []
    with job_lock:
        for key, job in list(jobs.items()):
            if job["status"] in {"ready", "error"} and now - job["updated"] > JOB_TTL:
                expired_dirs.append(Path(job["directory"]))
                jobs.pop(key, None)
    for folder in expired_dirs:
        shutil.rmtree(folder, ignore_errors=True)


def analyze(video_id: str, url: str) -> dict:
    options = get_ydl_options()
    options["skip_download"] = True
    with YoutubeDL(options) as dl:
        info = dl.extract_info(url, download=False)
    if not isinstance(info, dict) or info.get("_type") == "playlist":
        raise ValueError("Informe o link de um vídeo individual, não de uma playlist.")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
        raise ValueError("Transmissões ao vivo não são compatíveis com esta versão.")
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > MAX_DURATION_SECONDS:
        raise ValueError("Por segurança, esta versão aceita vídeos de até 4 horas.")
    heights = available_heights(info)
    if not heights:
        raise ValueError("Não foram encontradas opções de vídeo disponíveis.")
    result = {
        "id": video_id,
        "title": str(info.get("title") or "Vídeo do YouTube")[:250],
        "channel": str(info.get("uploader") or info.get("channel") or "YouTube")[:130],
        "duration": int(duration) if duration else None,
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "video_qualities": heights,
        "audio_qualities": AUDIO_QUALITIES,
    }
    with cache_lock:
        video_cache[video_id] = {**result, "created": time.time()}
    return result


def set_job(job_id: str, **changes) -> None:
    with job_lock:
        if job_id in jobs:
            jobs[job_id].update(changes, updated=time.time())


def run_download(job_id: str) -> None:
    with job_lock:
        job = jobs[job_id].copy()
    folder = Path(job["directory"])
    try:
        folder.mkdir(parents=True, exist_ok=True)
        options = get_ydl_options()
        options.update({
            "outtmpl": str(folder / "%(id)s.%(ext)s"),
            "overwrites": True,
            "progress_hooks": [lambda progress: on_progress(job_id, progress)],
        })
        if job["mode"] == "mp3":
            options["format"] = "bestaudio/best"
            options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(job["quality"]),
            }]
        else:
            height = job["quality"]
            # Prioriza H.264/MP4 + M4A; formatos de fallback dependem de FFmpeg.
            options["format"] = (
                f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]"
                f"/best[height={height}][ext=mp4]"
                f"/bestvideo[height={height}]+bestaudio"
                f"/best[height={height}]"
            )
            options["merge_output_format"] = "mp4"
            options["postprocessors"] = [{
                "key": "FFmpegVideoConvertor", "preferedformat": "mp4",
            }]
        set_job(job_id, status="processing", phase="Preparando download", progress=0)
        with YoutubeDL(options) as dl:
            dl.download([f"https://www.youtube.com/watch?v={job['video_id']}"])
        extension = ".mp3" if job["mode"] == "mp3" else ".mp4"
        outputs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == extension]
        if not outputs:
            raise RuntimeError("A conversão terminou, mas não foi gerado o arquivo esperado.")
        output = max(outputs, key=lambda p: p.stat().st_size)
        if output.stat().st_size > MAX_FILESIZE:
            raise RuntimeError("O arquivo excedeu o limite de 2 GB.")
        set_job(job_id, status="ready", phase="Arquivo pronto", progress=100, filepath=str(output))
    except Exception as exc:
        set_job(job_id, status="error", error=friendly_error(exc), phase="Falha no processamento")
        shutil.rmtree(folder, ignore_errors=True)


def on_progress(job_id: str, progress: dict) -> None:
    status = progress.get("status")
    if status == "downloading":
        done = float(progress.get("downloaded_bytes") or 0)
        total = float(progress.get("total_bytes") or progress.get("total_bytes_estimate") or 0)
        if done > MAX_FILESIZE:
            raise RuntimeError("O arquivo excedeu o limite de 2 GB.")
        pct = round(min(94, (done / total) * 94), 1) if total else 0
        set_job(job_id, status="processing", phase="Baixando mídia", progress=pct)
    elif status == "finished":
        set_job(job_id, status="processing", phase="Convertendo e finalizando", progress=95)


def delete_download(job_id: str, folder: Path) -> None:
    with job_lock:
        jobs.pop(job_id, None)
    shutil.rmtree(folder, ignore_errors=True)


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
        "deno": bool(shutil.which("deno")),
    }


@app.post("/api/info")
def info(payload: AnalyzeRequest):
    cleanup_expired()
    try:
        video_id, url = normalize_youtube_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return analyze(video_id, url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=friendly_error(exc)) from exc


@app.post("/api/jobs")
def create_job(payload: DownloadRequest):
    cleanup_expired()
    if not ID_RE.fullmatch(payload.video_id):
        raise HTTPException(status_code=400, detail="Vídeo inválido.")
    if payload.mode not in {"mp3", "mp4"}:
        raise HTTPException(status_code=400, detail="Formato inválido.")
    with cache_lock:
        metadata = video_cache.get(payload.video_id)
    if metadata is None or time.time() - metadata["created"] > CACHE_TTL:
        raise HTTPException(status_code=400, detail="Analise o link novamente antes de baixar.")
    valid_qualities = metadata["audio_qualities"] if payload.mode == "mp3" else metadata["video_qualities"]
    if payload.quality not in valid_qualities:
        raise HTTPException(status_code=400, detail="Qualidade não disponível neste vídeo.")
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise HTTPException(status_code=503, detail="FFmpeg não encontrado no aplicativo.")
    with job_lock:
        busy = sum(job["status"] in {"queued", "processing"} for job in jobs.values())
        if busy >= MAX_CONCURRENT_JOBS:
            raise HTTPException(status_code=429, detail="Já existem dois downloads em andamento. Tente novamente ao concluir.")
        job_id = uuid.uuid4().hex
        now = time.time()
        jobs[job_id] = {
            "video_id": payload.video_id,
            "title": metadata["title"],
            "mode": payload.mode,
            "quality": payload.quality,
            "status": "queued",
            "phase": "Na fila",
            "progress": 0,
            "error": None,
            "filepath": None,
            "directory": str(DOWNLOAD_DIR / job_id),
            "created": now,
            "updated": now,
        }
    executor.submit(run_download, job_id)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    cleanup_expired()
    with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Download não encontrado ou expirado.")
        return {key: job[key] for key in ["status", "phase", "progress", "error", "mode"]}


@app.get("/api/files/{job_id}")
def fetch_file(job_id: str, background_tasks: BackgroundTasks):
    with job_lock:
        job = jobs.get(job_id)
        if job is None or job["status"] != "ready":
            raise HTTPException(status_code=404, detail="Arquivo não encontrado ou ainda não está pronto.")
        path = Path(job["filepath"])
        mode = job["mode"]
        title = job["title"]
        directory = Path(job["directory"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    safe_title = SAFE_FILENAME_RE.sub("", title).strip(" .")[:95] or "video"
    background_tasks.add_task(delete_download, job_id, directory)
    return FileResponse(
        path,
        filename=f"{safe_title}.{mode}",
        media_type="audio/mpeg" if mode == "mp3" else "video/mp4",
        background=background_tasks,
    )
