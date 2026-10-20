"""RTSP カメラ向けの小さな道具箱"""

from video_kit.capture_options import apply_low_latency_capture_options

# OpenCV は import 時に OPENCV_FFMPEG_CAPTURE_OPTIONS を読むことがあるため、
# サブモジュールが cv2 を import するより先にここで設定する
apply_low_latency_capture_options()

__version__ = "0.1.0"
