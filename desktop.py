"""Ponto de entrada para ClipFlow portátil (Windows).

O servidor só escuta em 127.0.0.1, nunca publica uma porta na internet.
Na versão compilada, FFmpeg, FFprobe e Deno já estão dentro do executável/pasta.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def configure_embedded_tools() -> None:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    tool_dir = root / "vendor"
    if tool_dir.is_dir():
        os.environ["PATH"] = str(tool_dir) + os.pathsep + os.environ.get("PATH", "")


def choose_local_port() -> int:
    """Porta local livre. O endereço é mostrado para o usuário no console."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def open_browser_when_ready(port: int) -> None:
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.15)
    print(f"Nao foi possivel abrir o navegador automaticamente. Acesse {url}")


def main() -> None:
    configure_embedded_tools()
    import uvicorn
    from server import app

    port = choose_local_port()
    print("\n=== ClipFlow - Edicao Portatil ===")
    print(f"Endereco: http://127.0.0.1:{port}")
    print("Mantenha esta janela aberta enquanto estiver usando o site.")
    print("Feche a janela ou pressione Ctrl+C para encerrar.\n")
    threading.Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
