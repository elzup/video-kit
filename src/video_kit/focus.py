"""
RTSP カメラのライブビュー + ピント合わせ支援

複数カメラを並べて表示し、鮮鋭度 (Laplacian 分散) をリアルタイム表示する。
レンズを回しながら数値のピークを探す用途。

キー操作:
    q / ESC : 終了
    r       : ピーク値をリセット
    c       : 魚眼円の検出表示を切り替え
    f       : 計測領域を 中央 / 全体 で切り替え

鮮鋭度の目安 (中央領域):
    < 100   ピンボケ
    100-300 甘い
    > 300   実用域
    ピークを探すのが目的なので、絶対値より「回して上がるか」を見る。
"""

import time
from dataclasses import dataclass

import cv2
import numpy as np

from video_kit.fisheye import detect_circle
from video_kit.stream_reader import StreamReader

SOFT_THRESHOLD = 100.0
OK_THRESHOLD = 300.0
# RTSP の初回接続はキーフレーム待ちで数秒かかる。2 台同時でも収まる長さ
CONNECT_TIMEOUT_SEC = 15
# imshow の描画待ち。短すぎると描画が CPU を占有して受信スレッドが痩せる
WAIT_KEY_MS = 30
KEY_ESC = 27

Roi = tuple[int, int, int, int]


@dataclass
class ViewState:
    show_circle: bool = True
    center_mode: bool = True


def sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def grade(value: float) -> tuple[str, tuple[int, int, int]]:
    """鮮鋭度から (ラベル, BGR色) を返す"""
    if value < SOFT_THRESHOLD:
        return "PINBOKE", (60, 60, 255)
    if value < OK_THRESHOLD:
        return "SOFT", (60, 200, 255)
    return "OK", (80, 255, 80)


def measure_roi(frame: np.ndarray, roi_size: int, center_mode: bool) -> Roi:
    h, w = frame.shape[:2]
    if not center_mode:
        return (0, 0, w, h)
    side = min(roi_size, h, w)
    return ((w - side) // 2, (h - side) // 2, side, side)


def draw_circle(view: np.ndarray, frame: np.ndarray, scale: float) -> None:
    try:
        cx, cy, r = detect_circle(frame)
    except ValueError:
        # 魚眼でないレンズや暗いシーンでは検出できない。表示を省くだけでよい
        return
    color = (0, 200, 255)
    cv2.circle(view, (int(cx * scale), int(cy * scale)), int(r * scale), color, 2)
    cv2.putText(
        view,
        f"D={2 * r:.0f}px c=({cx:.0f},{cy:.0f})",
        (10, view.shape[0] - 14),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
    )


def annotate(
    frame: np.ndarray,
    name: str,
    value: float,
    peak: float,
    roi: Roi,
    state: ViewState,
    width: int,
) -> np.ndarray:
    """1 カメラ分の表示画像を作る"""
    scale = width / frame.shape[1]
    view = cv2.resize(frame, (width, int(frame.shape[0] * scale)))

    x, y, w, h = roi
    cv2.rectangle(
        view,
        (int(x * scale), int(y * scale)),
        (int((x + w) * scale), int((y + h) * scale)),
        (255, 255, 0),
        2,
    )
    if state.show_circle:
        draw_circle(view, frame, scale)

    label, color = grade(value)
    mode = "center" if state.center_mode else "full"
    cv2.rectangle(view, (0, 0), (view.shape[1], 78), (0, 0, 0), -1)
    cv2.putText(
        view, f"{name}  {value:7.1f}  {label}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2
    )
    cv2.putText(
        view,
        f"peak {peak:7.1f}   roi={mode}",
        (10, 62),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (200, 200, 200),
        1,
    )

    # ピークに対する現在値のバー
    ratio = 0.0 if peak <= 0 else min(1.0, value / peak)
    bar_w = int((view.shape[1] - 20) * ratio)
    cv2.rectangle(view, (10, 70), (10 + bar_w, 76), color, -1)
    return view


def no_signal_panel(name: str, width: int) -> np.ndarray:
    blank = np.zeros((width * 9 // 16, width, 3), np.uint8)
    cv2.putText(
        blank, f"{name}: no signal", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 60, 255), 2
    )
    return blank


def stack_panels(panels: list[np.ndarray]) -> np.ndarray:
    """高さを揃えて横に並べる"""
    height = max(p.shape[0] for p in panels)
    padded = [
        cv2.copyMakeBorder(p, 0, height - p.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        for p in panels
    ]
    return np.hstack(padded)


def connect(cameras: list[tuple[str, str]]) -> list[StreamReader]:
    """全カメラに接続し、最初のフレームが来るまで待つ"""
    readers = [StreamReader(n, u).start() for n, u in cameras]
    print("接続中...")
    deadline = time.time() + CONNECT_TIMEOUT_SEC
    while time.time() < deadline:
        if all(r.read() is not None or r.error for r in readers):
            break
        time.sleep(0.2)

    for r in readers:
        if r.error:
            print(f"  {r.name}: {r.error} ({r.url})")
        elif r.read() is None:
            print(f"  {r.name}: フレームを取得できません ({r.url})")
        else:
            print(f"  {r.name}: OK")
    return readers


def render(
    readers: list[StreamReader],
    peaks: dict[str, float],
    state: ViewState,
    roi_size: int,
    width: int,
) -> np.ndarray:
    panels = []
    for r in readers:
        frame = r.read()
        if frame is None:
            panels.append(no_signal_panel(r.name, width))
            continue
        roi = measure_roi(frame, roi_size, state.center_mode)
        x, y, rw, rh = roi
        gray = cv2.cvtColor(frame[y : y + rh, x : x + rw], cv2.COLOR_BGR2GRAY)
        value = sharpness(gray)
        peaks[r.name] = max(peaks[r.name], value)
        panels.append(annotate(frame, r.name, value, peaks[r.name], roi, state, width))
    return stack_panels(panels)


def run(cameras: list[tuple[str, str]], width: int, roi_size: int) -> int:
    readers = connect(cameras)
    if all(r.read() is None for r in readers):
        print("どのカメラにも接続できませんでした。")
        for r in readers:
            r.stop()
        return 1

    print()
    print("レンズを回しながら数値のピークを探してください。")
    print("  q/ESC 終了   r ピークリセット   c 円表示切替   f 計測領域切替")

    peaks = {r.name: 0.0 for r in readers}
    state = ViewState()
    window = "focus assist  (q:quit  r:reset  c:circle  f:roi)"
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)

    try:
        while True:
            cv2.imshow(window, render(readers, peaks, state, roi_size, width))
            key = cv2.waitKey(WAIT_KEY_MS) & 0xFF
            if key in (ord("q"), KEY_ESC):
                break
            if key == ord("r"):
                peaks = {k: 0.0 for k in peaks}
            if key == ord("c"):
                state.show_circle = not state.show_circle
            if key == ord("f"):
                state.center_mode = not state.center_mode
    except KeyboardInterrupt:
        pass
    finally:
        for r in readers:
            r.stop()
        cv2.destroyAllWindows()

    print("\n最終ピーク値:")
    for name, peak in peaks.items():
        label, _ = grade(peak)
        print(f"  {name}: {peak:.1f}  {label}")
    return 0
