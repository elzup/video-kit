"""
常に最新フレームだけを保持する RTSP リーダー

RTSP はバッファが溜まると数秒遅れるため、専用スレッドで読み続けて
最新の 1 枚だけを持つ。
"""

import threading
import time
from collections.abc import Callable

import cv2
import numpy as np

# 読み取り失敗時の待ち。0 だと切断中にスレッドが CPU を空回りする
RETRY_WAIT_SEC = 0.05


class StreamReader:
    """常に最新フレームだけを保持する RTSP リーダー

    on_frame を渡すと、受信したフレームを 1 枚も落とさずに
    (フレーム, 受信時刻 perf_counter) で受け取れる。遅延計測のように
    フレーム単位の到着時刻が要る用途向け。
    """

    def __init__(
        self,
        name: str,
        url: str,
        on_frame: Callable[[np.ndarray, float], None] | None = None,
    ):
        self.name = name
        self.url = url
        self.frame: np.ndarray | None = None
        self.stamp: float = 0.0
        self.on_frame = on_frame
        self.lock = threading.Lock()
        self.running = True
        self.frames_read = 0
        self.error: str | None = None
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> "StreamReader":
        self.thread.start()
        return self

    def _loop(self) -> None:
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            # バックエンドによっては未対応。低遅延化の補助なので無くても動く
            pass
        if not cap.isOpened():
            self.error = "接続できません"
            return
        while self.running:
            ok, frame = cap.read()
            stamp = time.perf_counter()
            if not ok:
                time.sleep(RETRY_WAIT_SEC)
                continue
            with self.lock:
                self.frame = frame
                self.stamp = stamp
                self.frames_read += 1
            if self.on_frame is not None:
                self.on_frame(frame, stamp)
        cap.release()

    def read(self) -> np.ndarray | None:
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def read_stamped(self) -> tuple[np.ndarray | None, float]:
        """(最新フレーム, その受信時刻) を返す。未受信なら (None, 0.0)"""
        with self.lock:
            if self.frame is None:
                return None, 0.0
            return self.frame.copy(), self.stamp

    def stop(self) -> None:
        self.running = False
