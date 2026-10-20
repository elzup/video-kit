"""
ピント合わせのブラウザ表示

OpenCV のウィンドウは文字を画素に焼き込むため、Retina では文字がぼやけ、
日本語も出せない。受信と計算はそのままに、表示だけを HTML に任せる。

    GET  /               画面
    GET  /stream/<i>     カメラ i の MJPEG
    GET  /stats          全カメラの鮮鋭度・ピーク・ROI・魚眼円 (JSON)
    POST /action/<name>  reset / circle / roi
"""

import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

import cv2

from video_kit.fisheye import detect_circle
from video_kit.focus import connect, grade, measure_roi, sharpness
from video_kit.stream_reader import StreamReader

# 計測の周期。表示側のポーリング (100ms) より少し速ければ十分
MEASURE_INTERVAL_SEC = 1 / 15
# 魚眼円の検出は 1 回数十 ms かかるので間引く
CIRCLE_INTERVAL_SEC = 1.0
# ブラウザへ送る映像の上限幅。計測は元解像度で行うので見た目だけの縮小
STREAM_MAX_WIDTH = 1280
STREAM_JPEG_QUALITY = 85
STREAM_INTERVAL_SEC = 1 / 30


class FocusMeter:
    """全カメラの鮮鋭度を裏で測り続け、最新の結果を持つ"""

    def __init__(self, readers: list[StreamReader], roi_size: int):
        self.readers = readers
        self.roi_size = roi_size
        self.center_mode = True
        self.show_circle = True
        self.lock = threading.Lock()
        self.peaks = {r.name: 0.0 for r in readers}
        self.stats: list[dict] = []
        self.circles: dict[str, dict | None] = {r.name: None for r in readers}
        self.circle_at = 0.0
        self.running = True

    def start(self) -> "FocusMeter":
        threading.Thread(target=self._loop, daemon=True).start()
        return self

    def _loop(self) -> None:
        while self.running:
            self._measure()
            time.sleep(MEASURE_INTERVAL_SEC)

    def _measure(self) -> None:
        now = time.time()
        update_circle = self.show_circle and now - self.circle_at >= CIRCLE_INTERVAL_SEC
        stats = []
        for r in self.readers:
            frame = r.read()
            if frame is None:
                stats.append({"name": r.name, "signal": False})
                continue
            h, w = frame.shape[:2]
            x, y, rw, rh = measure_roi(frame, self.roi_size, self.center_mode)
            gray = cv2.cvtColor(frame[y : y + rh, x : x + rw], cv2.COLOR_BGR2GRAY)
            value = sharpness(gray)
            if update_circle:
                self.circles[r.name] = _circle_or_none(frame)
            with self.lock:
                self.peaks[r.name] = max(self.peaks[r.name], value)
                peak = self.peaks[r.name]
            stats.append(
                {
                    "name": r.name,
                    "signal": True,
                    "value": value,
                    "peak": peak,
                    "grade": grade(value)[0],
                    "width": w,
                    "height": h,
                    "roi": [x, y, rw, rh],
                    "circle": self.circles[r.name] if self.show_circle else None,
                }
            )
        if update_circle:
            self.circle_at = now
        with self.lock:
            self.stats = stats

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "cameras": self.stats,
                "centerMode": self.center_mode,
                "showCircle": self.show_circle,
            }

    def act(self, name: str) -> bool:
        with self.lock:
            if name == "reset":
                self.peaks = {k: 0.0 for k in self.peaks}
            elif name == "circle":
                self.show_circle = not self.show_circle
                self.circle_at = 0.0
            elif name == "roi":
                self.center_mode = not self.center_mode
                self.peaks = {k: 0.0 for k in self.peaks}
            else:
                return False
        return True


def _circle_or_none(frame) -> dict | None:
    try:
        cx, cy, r = detect_circle(frame)
    except ValueError:
        # 魚眼でないレンズや暗いシーンでは検出できない。表示しないだけでよい
        return None
    return {"cx": cx, "cy": cy, "r": r}


def _encode(frame) -> bytes:
    h, w = frame.shape[:2]
    if w > STREAM_MAX_WIDTH:
        frame = cv2.resize(frame, (STREAM_MAX_WIDTH, int(h * STREAM_MAX_WIDTH / w)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_JPEG_QUALITY])
    return buf.tobytes() if ok else b""


def make_handler(meter: FocusMeter):
    page = files("video_kit").joinpath("focus.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # アクセスごとのログは MJPEG とポーリングで埋まるので出さない
            pass

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(page, "text/html; charset=utf-8")
            elif self.path == "/stats":
                self._send(json.dumps(meter.snapshot()).encode(), "application/json")
            elif self.path.startswith("/stream/"):
                self._stream(self.path.removeprefix("/stream/"))
            else:
                self._send(b"not found", "text/plain", 404)

        def do_POST(self) -> None:
            name = self.path.removeprefix("/action/")
            ok = self.path.startswith("/action/") and meter.act(name)
            self._send(b"ok" if ok else b"unknown", "text/plain", 200 if ok else 404)

        def _stream(self, index: str) -> None:
            if not index.isdigit() or int(index) >= len(meter.readers):
                self._send(b"not found", "text/plain", 404)
                return
            reader = meter.readers[int(index)]
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while meter.running:
                    frame = reader.read()
                    if frame is not None:
                        jpg = _encode(frame)
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg + b"\r\n")
                    time.sleep(STREAM_INTERVAL_SEC)
            except (BrokenPipeError, ConnectionResetError):
                # タブを閉じた・再読み込みしただけ。このストリームを終えればよい
                return

    return Handler


def run(cameras: list[tuple[str, str]], roi_size: int, port: int, open_browser: bool) -> int:
    readers = connect(cameras)
    if all(r.read() is None for r in readers):
        print("どのカメラにも接続できませんでした。")
        for r in readers:
            r.stop()
        return 1

    meter = FocusMeter(readers, roi_size).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(meter))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"\nブラウザで開いています: {url}")
    print("終了は Ctrl+C")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        meter.running = False
        server.server_close()
        for r in readers:
            r.stop()

    print("\n最終ピーク値:")
    for name, peak in meter.peaks.items():
        print(f"  {name}: {peak:.1f}  {grade(peak)[0]}")
    return 0
