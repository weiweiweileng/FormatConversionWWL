# -*- coding: utf-8 -*-
"""格式转换工坊 · 本地服务入口。

电脑、手机（同一局域网）均可通过浏览器访问：
    python app.py [--port 8765] [--no-browser]
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image

from core.registry import REGISTRY, unique_path

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# 无窗口启动（pythonw）时 stdout/stderr 为 None，print 会报错 → 重定向到日志文件
if sys.stdout is None or sys.stderr is None:
    _log_dir = BASE_DIR / "logs"
    _log_dir.mkdir(exist_ok=True)
    _log = open(_log_dir / "server.log", "a", buffering=1, encoding="utf-8", errors="replace")
    _log.write(f"\n===== 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

app = Flask(__name__, static_folder=str(BASE_DIR / "web"), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB

# ---------------------------------------------------------------- 状态管理

_lock = threading.Lock()
_files: list[dict] = []          # {id,name,path,size,ext,animated,frames,status,output,error}
_thumbs: dict[str, bytes] = {}
_job: dict | None = None         # 当前/最近一次转换任务
SUPPORTED_EXTS = REGISTRY.supported_source_exts()


def _probe(path: Path) -> dict:
    size = path.stat().st_size
    animated, frames = False, 1
    try:
        with Image.open(path) as im:
            frames = getattr(im, "n_frames", 1)
            animated = frames > 1
    except Exception:
        pass
    return {
        "id": uuid.uuid4().hex[:12],
        "name": path.name,
        "path": str(path),
        "size": size,
        "ext": path.suffix.lower(),
        "animated": animated,
        "frames": frames,
        "status": "pending",
        "output": None,
        "error": None,
        "target_label": None,
    }


def _add_path_entry(path: Path) -> bool:
    p = path.resolve()
    if p.suffix.lower() not in SUPPORTED_EXTS or not p.is_file():
        return False
    if any(f["path"] == str(p) for f in _files):
        return False
    _files.append(_probe(p))
    return True


def _scan_dir(dir_path: Path) -> tuple[int, int]:
    """递归扫描文件夹；跳过本工具的输出目录（converted_*、output）与隐藏目录。"""
    added = skipped = 0
    for p in sorted(dir_path.rglob("*")):
        if p.is_dir():
            continue
        parent_parts = p.relative_to(dir_path).parts[:-1]
        is_tool_output = any(
            part.startswith("converted") or part == "output" for part in parent_parts
        )
        if is_tool_output or any(part.startswith(".") for part in parent_parts):
            skipped += 1
            continue
        if _add_path_entry(p):
            added += 1
        else:
            skipped += 1
    return added, skipped


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    name = "".join(c for c in name if c not in '<>:"/\\|?*' and ord(c) >= 32)
    return (name[:180] or "file")


def _worker(item: dict, target_key: str, out_dir: Path | None) -> None:
    with _lock:
        item["status"] = "running"
    src = Path(item["path"])
    dest_dir = out_dir if out_dir is not None else BASE_DIR / "output"
    target = REGISTRY.find(target_key)
    dst = unique_path(dest_dir, src.stem, target.ext)
    try:
        out = REGISTRY.convert(target_key, src, dst)
        with _lock:
            item["status"] = "done"
            item["output"] = str(out)
    except Exception as e:  # 单个文件失败不影响整批
        with _lock:
            item["status"] = "error"
            item["error"] = str(e) or e.__class__.__name__


def _finish_callback(future) -> None:
    with _lock:
        _job["remaining"] -= 1
        if _job["remaining"] <= 0:
            _job["running"] = False
            import time
            _job["finished_at"] = time.time()


# ---------------------------------------------------------------- 心跳与自动退出
# 页面每 2 秒 POST /api/heartbeat；一旦有页面连上来过（started），
# 之后超过 hb_timeout 秒没有任何心跳（所有浏览器页面都已关闭）且没有
# 正在进行的转换时，服务自动退出。多设备场景：任一页面仍在即持续存活。

_hb = {"last": None, "started": False}
_hb_lock = threading.Lock()


@app.post("/api/heartbeat")
def api_heartbeat():
    with _hb_lock:
        _hb["last"] = time.time()
        _hb["started"] = True
    return jsonify({"ok": True})


def _watchdog(hb_timeout: float) -> None:
    while True:
        time.sleep(2)
        with _hb_lock:
            last, started = _hb["last"], _hb["started"]
        if not started or last is None:
            continue
        if time.time() - last < hb_timeout:
            continue
        with _lock:
            converting = bool(_job and _job.get("running"))
        if converting:
            continue  # 等本批转换结束后再退出
        print(f"[watchdog] {hb_timeout:.0f}s 无页面心跳，自动退出服务")
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os._exit(0)


# ---------------------------------------------------------------- API

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/formats")
def api_formats():
    return jsonify({"targets": REGISTRY.list_targets()})


@app.post("/api/upload")
def api_upload():
    saved = skipped = 0
    for f in request.files.getlist("files"):
        name = _sanitize_filename(f.filename or "file")
        if Path(name).suffix.lower() not in SUPPORTED_EXTS:
            skipped += 1
            continue
        folder = UPLOAD_DIR / uuid.uuid4().hex[:12]
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / name
        f.save(dest)
        with _lock:
            if _add_path_entry(dest):
                saved += 1
            else:
                skipped += 1
    return jsonify({"added": saved, "skipped": skipped})


@app.post("/api/add-paths")
def api_add_paths():
    data = request.get_json(force=True)
    added = skipped = 0
    for raw in data.get("paths", []):
        p = Path(raw.strip().strip('"'))
        if p.is_dir():
            a, s = _scan_dir(p)
            added += a
            skipped += s
        elif p.is_file():
            if _add_path_entry(p):
                added += 1
            else:
                skipped += 1
        else:
            skipped += 1
    return jsonify({"added": added, "skipped": skipped})


@app.post("/api/remove/<item_id>")
def api_remove(item_id):
    with _lock:
        _files[:] = [f for f in _files if f["id"] != item_id]
    return jsonify({"ok": True})


@app.post("/api/clear")
def api_clear():
    with _lock:
        if _job and _job.get("running"):
            return jsonify({"ok": False, "error": "转换进行中，无法清空"}), 409
        _files.clear()
        _thumbs.clear()
    return jsonify({"ok": True})


@app.get("/api/thumb/<item_id>")
def api_thumb(item_id):
    with _lock:
        item = next((f for f in _files if f["id"] == item_id), None)
    if item is None:
        return "", 404
    png = _thumbs.get(item_id)
    if png is None:
        try:
            with Image.open(item["path"]) as im:
                im = im.convert("RGBA")
                im.thumbnail((96, 96))
            buf = io.BytesIO()
            im.save(buf, "PNG")
            png = buf.getvalue()
            _thumbs[item_id] = png
        except Exception:
            return "", 404
    return send_file(io.BytesIO(png), mimetype="image/png")


@app.post("/api/convert")
def api_convert():
    global _job
    data = request.get_json(force=True)
    target_key = data.get("target")
    target = REGISTRY.find(target_key)
    if target is None or not target.available:
        return jsonify({"error": f"未知或不可用的目标格式: {target_key}"}), 400

    output_mode = data.get("outputMode", "beside")
    custom_dir = (data.get("outputDir") or "").strip()
    out_dir: Path | None = None
    if output_mode == "custom":
        if not custom_dir:
            return jsonify({"error": "请填写输出目录"}), 400
        out_dir = Path(custom_dir)

    with _lock:
        if _job and _job.get("running"):
            return jsonify({"error": "已有转换正在进行中"}), 409
        # 待转换 = 新文件 + 上次失败的可重试文件
        pending = [f for f in _files if f["status"] in ("pending", "error")]
        if not pending:
            return jsonify({"error": "没有待转换的文件"}), 400
        for f in pending:
            f["status"] = "queued"
            f["target_label"] = target.label
        _job = {
            "target": target_key,
            "target_label": target.label,
            "running": True,
            "total": len(pending),
            "remaining": len(pending),
            "output_mode": output_mode,
            "output_dir": str(out_dir) if out_dir else None,
            "finished_at": None,
        }
        pool = ThreadPoolExecutor(max_workers=4)
        for f in pending:
            fut = pool.submit(_worker, f, target_key, out_dir)
            fut.add_done_callback(_finish_callback)
        pool.shutdown(wait=False)
    return jsonify({"ok": True, "total": len(pending)})


@app.get("/api/status")
def api_status():
    with _lock:
        files = [dict(f) for f in _files]
        job = dict(_job) if _job else None
    counts = {"pending": 0, "queued": 0, "running": 0, "done": 0, "error": 0}
    for f in files:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    return jsonify({
        "files": files,
        "job": job,
        "counts": counts,
        "supportedExts": sorted(SUPPORTED_EXTS),
    })


@app.post("/api/open-output")
def api_open_output():
    with _lock:
        job = dict(_job) if _job else None
        done = [f for f in _files if f["status"] == "done" and f.get("output")]
    target_dir = None
    if job and job.get("output_dir"):
        target_dir = job["output_dir"]
    elif done:
        target_dir = str(Path(done[0]["output"]).parent)
    if not target_dir or not Path(target_dir).is_dir():
        return jsonify({"error": "没有可打开的输出目录"}), 400
    os.startfile(target_dir)  # noqa  Windows 资源管理器打开
    return jsonify({"ok": True})


@app.post("/api/pick-folder")
def api_pick_folder():
    """在电脑上弹出系统目录选择框（手机端请直接手填路径）。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory()
        root.destroy()
    except Exception:
        return jsonify({"error": "本机无法弹出目录选择框，请手动填写路径"}), 500
    return jsonify({"folder": folder or ""})


# ---------------------------------------------------------------- 入口

_port = 8765


def main() -> None:
    global _port
    parser = argparse.ArgumentParser(description="格式转换工坊")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--hb-timeout", type=float, default=30,
                        help="页面心跳超时秒数，超时且无转换任务时自动退出服务")
    args = parser.parse_args()
    _port = args.port

    # 已有实例在运行时，直接打开页面即可，不再起第二个服务
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        already = s.connect_ex(("127.0.0.1", args.port)) == 0
    if already:
        print(f"端口 {args.port} 已有服务实例，直接打开页面")
        webbrowser.open(f"http://127.0.0.1:{args.port}")
        return

    threading.Thread(target=_watchdog, args=(args.hb_timeout,), daemon=True).start()

    local = f"http://127.0.0.1:{args.port}"
    print("=" * 52)
    print("  格式转换工坊已启动")
    print(f"  访问地址:  {local}")
    print(f"  所有页面关闭 {args.hb_timeout:.0f}s 后服务自动退出")
    print("=" * 52)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(local)).start()
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
