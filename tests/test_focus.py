import numpy as np

from video_kit.focus import grade, measure_roi, sharpness


def test_sharp_image_scores_higher_than_flat():
    flat = np.full((100, 100), 128, np.uint8)
    checker = (np.indices((100, 100)).sum(axis=0) % 2 * 255).astype(np.uint8)
    assert sharpness(checker) > sharpness(flat)
    assert sharpness(flat) == 0.0


def test_grade_thresholds():
    assert grade(50)[0] == "PINBOKE"
    assert grade(150)[0] == "SOFT"
    assert grade(500)[0] == "OK"


def test_measure_roi_center_is_clamped_to_frame():
    frame = np.zeros((300, 400, 3), np.uint8)
    assert measure_roi(frame, 500, center_mode=True) == (50, 0, 300, 300)
    assert measure_roi(frame, 500, center_mode=False) == (0, 0, 400, 300)
