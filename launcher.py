"""Standalone Desktop Launcher & Windows Packaging Entrypoint for BidGuard."""

from __future__ import annotations

import argparse
import io
import json
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import httpx
import uvicorn


def _configure_frozen_streams() -> None:
    """Ensure stdout/stderr are valid writable streams in PyInstaller --noconsole mode."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from backend.config import DATA_DIR, ensure_data_dirs

    log_stream: Any
    try:
        ensure_data_dirs()
        log_stream = (DATA_DIR / "bidguard.log").open("a", encoding="utf-8", buffering=1)
    except OSError:
        log_stream = io.StringIO()

    if sys.stdout is None:
        sys.stdout = log_stream
    if sys.stderr is None:
        sys.stderr = log_stream


def find_available_port(host: str = "127.0.0.1", preferred: int = 8000) -> int:
    """Return an available TCP port, checking preferred then 8001..8050, or ephemeral 0."""
    candidates = [preferred, *range(8001, 8051)]
    for port in candidates:
        if port <= 0:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def is_bidguard_running(host: str, port: int) -> bool:
    """Return True if an active BidGuard server already answers /api/health on host:port."""
    try:
        resp = httpx.get(f"http://{host}:{port}/api/health", timeout=0.5)
        return resp.status_code == 200 and resp.json().get("app") == "bidguard"
    except Exception:
        return False


def _find_msedge_executable() -> str | None:
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return shutil.which("msedge")


def open_workbench_window(url: str, app_mode: bool = True) -> None:
    """Open BidGuard in Edge --app chromeless window on Windows when available, else default browser."""
    if sys.platform == "win32" and app_mode:
        edge = _find_msedge_executable()
        if edge:
            try:
                subprocess.Popen([edge, f"--app={url}"])
                return
            except OSError:
                pass
    webbrowser.open(url)


def _open_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _start_uvicorn_thread(host: str, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    from backend.main import app

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="bidguard-uvicorn", daemon=True)
    thread.start()
    return server, thread


def _wait_for_health(host: str, port: int, thread: threading.Thread, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    url = f"http://{host}:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=0.5)
            if resp.status_code == 200 and resp.json().get("app") == "bidguard":
                return
        except Exception:
            pass
        if not thread.is_alive():
            raise RuntimeError("Uvicorn server thread exited unexpectedly before becoming healthy")
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for BidGuard server health check on {url}")


def _verify_bundled_libraries() -> None:
    import docx
    import lxml.etree as etree
    import openpyxl
    import pymupdf
    from PIL import Image

    doc = docx.Document()
    doc.add_paragraph("ok")
    wb = openpyxl.Workbook()
    _ = wb.active
    pdf_doc = pymupdf.open()
    pdf_doc.close()
    _ = Image.new("RGB", (8, 8))
    root = etree.Element("ok")
    assert root.tag == "ok"


def _write_selftest_result(out_path: str, payload: dict[str, Any]) -> None:
    if not out_path:
        return
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_self_test(out_path: str) -> int:
    from backend.main import APP_VERSION

    port = find_available_port("127.0.0.1", preferred=18765)
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    try:
        server, thread = _start_uvicorn_thread("127.0.0.1", port)
        _wait_for_health("127.0.0.1", port, thread, timeout_s=15.0)

        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
            r_root = client.get("/")
            if r_root.status_code != 200 or "标书智检" not in r_root.text:
                raise RuntimeError(f"Unexpected SPA root response: status={r_root.status_code}")

            r_settings = client.get("/api/settings")
            if r_settings.status_code != 200:
                raise RuntimeError(f"Unexpected /api/settings status={r_settings.status_code}")

        _verify_bundled_libraries()

        payload = {"ok": True, "version": APP_VERSION, "port": port}
        _write_selftest_result(out_path, payload)
        print("SELF_TEST_OK")
        return 0
    except Exception as exc:
        _write_selftest_result(out_path, {"ok": False, "error": str(exc)})
        print(f"SELF_TEST_FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)


def _run_controller_window(url: str, data_dir: Path, server: uvicorn.Server) -> bool:
    """Launch compact desktop status/control window. Returns False if tkinter cannot initialize."""
    try:
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
            except Exception:
                pass

        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
    except Exception:
        return False

    root.title("标书智检 BidGuard")
    root.geometry("380x168")
    root.resizable(False, False)

    def shutdown() -> None:
        server.should_exit = True
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", shutdown)

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill=tk.BOTH, expand=True)

    title_lbl = ttk.Label(frame, text="标书智检 BidGuard", font=("Microsoft YaHei UI", 11, "bold") if sys.platform == "win32" else ("", 13, "bold"))
    title_lbl.pack(anchor=tk.W)

    status_lbl = ttk.Label(frame, text=f"● 运行中  {url}", foreground="#15803D")
    status_lbl.pack(anchor=tk.W, pady=(6, 14))

    btn_row1 = ttk.Frame(frame)
    btn_row1.pack(fill=tk.X, pady=(0, 8))
    ttk.Button(btn_row1, text="打开工作台", command=lambda: open_workbench_window(url, True)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
    ttk.Button(btn_row1, text="浏览器打开", command=lambda: open_workbench_window(url, False)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

    btn_row2 = ttk.Frame(frame)
    btn_row2.pack(fill=tk.X)
    ttk.Button(btn_row2, text="数据目录", command=lambda: _open_directory(data_dir)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
    ttk.Button(btn_row2, text="退出", command=shutdown).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))

    root.mainloop()
    return True


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BidGuard 标书智检 独立桌面启动器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="首选监听端口（默认 8000）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开窗口")
    parser.add_argument("--headless", action="store_true", help="无控制窗口，仅后台运行服务")
    parser.add_argument("--self-test", action="store_true", help="执行打包自检后自动退出")
    parser.add_argument("--self-test-out", default="", help="自检 JSON 结果输出路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    os.environ.setdefault("PYTHONUTF8", "1")
    _configure_frozen_streams()

    args = _parse_args(argv)
    if args.self_test:
        return _run_self_test(args.self_test_out)

    host = args.host
    if is_bidguard_running(host, args.port):
        if not args.no_browser:
            open_workbench_window(f"http://{host}:{args.port}", app_mode=True)
        return 0

    port = find_available_port(host, preferred=args.port)
    url = f"http://{host}:{port}"
    server, thread = _start_uvicorn_thread(host, port)
    try:
        _wait_for_health(host, port, thread, timeout_s=20.0)
        if not args.no_browser:
            open_workbench_window(url, app_mode=True)

        from backend.config import DATA_DIR, ensure_data_dirs

        ensure_data_dirs()
        launched_gui = False if args.headless else _run_controller_window(url, DATA_DIR, server)
        if not launched_gui:
            while not server.should_exit and thread.is_alive():
                time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
