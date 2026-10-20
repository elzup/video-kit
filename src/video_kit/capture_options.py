"""
OpenCV の FFmpeg バックエンドに低遅延の RTSP 設定を渡す

`cv2` を import する **前** に `apply_low_latency_capture_options()` を呼ぶこと。
OpenCV は環境変数 OPENCV_FFMPEG_CAPTURE_OPTIONS を読むが、import 後だと
効かないことがある。

各オプションの意味:

    rtsp_transport;tcp
        既定は UDP。パケットを落とすと HEVC の参照フレームが壊れ、
        灰色一色のフレームが出続ける (Could not find ref with POC)。

    reorder_queue_size;0
        **遅延の主犯。** 既定 -1 は「自動」で、パケット並べ替え用に
        かなりの数を溜め込む。RTSP ではこれが数百 ms になる。
        TCP なら順序は保証されるので 0 でよい。

    fflags;nobuffer
        デマクサ側の入力バッファリングを止める。

    flags;low_delay
        デコーダに低遅延モードを要求する (フレーム並べ替えを待たない)。

    max_delay;0
        パケット並べ替えの待ち時間の上限をゼロにする。

書式は OpenCV 独自で、`キー;値` を `|` で連結する。
"""

import os

LOW_LATENCY_RTSP = "|".join(
    [
        "rtsp_transport;tcp",
        "reorder_queue_size;0",
        "fflags;nobuffer",
        "flags;low_delay",
        "max_delay;0",
    ]
)


def apply_low_latency_capture_options(force: bool = False) -> str:
    """OPENCV_FFMPEG_CAPTURE_OPTIONS を設定して、設定値を返す

    Args:
        force: True なら既存の環境変数を上書きする。
            False (既定) では、呼び出し側が独自に指定していればそれを尊重する。
    """
    if force or not os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS"):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = LOW_LATENCY_RTSP
    return os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
