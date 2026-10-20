import cv2
import numpy as np
import pytest

from video_kit.fisheye import detect_circle


def test_detects_circle_cut_at_top_and_bottom():
    # 実機と同じく、円が上下で切れているフレーム
    img = np.zeros((360, 640, 3), np.uint8)
    cv2.circle(img, (320, 170), 230, (200, 200, 200), -1)
    cx, cy, r = detect_circle(img)
    assert cx == pytest.approx(320, abs=3)
    assert cy == pytest.approx(170, abs=3)
    assert r == pytest.approx(230, abs=3)


def test_blank_frame_raises():
    with pytest.raises(ValueError):
        detect_circle(np.zeros((360, 640, 3), np.uint8))
