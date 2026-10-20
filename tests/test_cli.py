from video_kit.cli import build_parser


def test_focus_defaults_to_browser():
    args = build_parser().parse_args(["focus", "1"])
    assert args.window is False
    assert args.port == 0


def test_focus_window_flag():
    args = build_parser().parse_args(["focus", "1", "--window"])
    assert args.window is True
