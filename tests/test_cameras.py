import pytest

from video_kit import cameras


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("VIDEO_KIT_CAMERA_URLS", raising=False)
    monkeypatch.delenv("VIDEO_KIT_CAMERA_IPS", raising=False)


def test_nothing_configured_returns_empty():
    assert cameras.get_cameras() == []
    assert cameras.describe_source() == "未設定"


def test_targets_accept_url_and_ip():
    assert cameras.get_cameras(["rtsp://h/x", "192.0.2.7"]) == [
        ("cam1", "rtsp://h/x"),
        ("cam7", "rtsp://192.0.2.7:5005/routecam"),
    ]


def test_ips_env_uses_routecam_url(monkeypatch):
    monkeypatch.setenv("VIDEO_KIT_CAMERA_IPS", "192.0.2.10, 192.0.2.11")
    assert cameras.get_cameras() == [
        ("cam10", "rtsp://192.0.2.10:5005/routecam"),
        ("cam11", "rtsp://192.0.2.11:5005/routecam"),
    ]


def test_urls_env_wins_over_ips_env(monkeypatch):
    monkeypatch.setenv("VIDEO_KIT_CAMERA_IPS", "192.0.2.1")
    monkeypatch.setenv("VIDEO_KIT_CAMERA_URLS", "rtsp://a/1, rtsp://b/2")
    assert cameras.get_cameras() == [("cam1", "rtsp://a/1"), ("cam2", "rtsp://b/2")]
    assert cameras.describe_source() == "VIDEO_KIT_CAMERA_URLS"
