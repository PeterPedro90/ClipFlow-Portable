"""Smoke tests for the Windows packaging setup (without executing Windows binaries)."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_desktop_module():
    spec = importlib.util.spec_from_file_location("clipflow_desktop_test", PROJECT_ROOT / "desktop.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portable_adds_embedded_binaries_to_path(monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("PATH", "OLD_PATH")
    module = load_desktop_module()
    module.configure_embedded_tools()
    assert os.environ["PATH"].startswith(str(vendor) + os.pathsep)
    assert os.environ["PATH"].endswith("OLD_PATH")


def test_windows_build_workflow_and_resources():
    workflow = (PROJECT_ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "scripts/build_windows.ps1").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "--onedir" in script
    for binary in ("ffmpeg.exe", "ffprobe.exe", "deno.exe"):
        assert binary in script
    assert "static;static" in script
