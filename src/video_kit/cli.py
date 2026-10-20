"""video-kit コマンドの入口"""

import argparse
import sys

from video_kit import __version__, cameras

# 2 台並べて 1920 幅の画面に収まる幅
DEFAULT_WIDTH = 760
# 1 台だけなら大きく出す
SINGLE_WIDTH = 1100


def cmd_focus(args: argparse.Namespace) -> int:
    from video_kit import focus

    targets = cameras.get_cameras(args.targets)
    if not targets:
        print("接続先がありません。URL か IP を渡してください:")
        print("  video-kit focus 192.0.2.10")
        print("IP が分からなければ: video-kit cameras")
        return 1
    if args.only:
        targets = [(n, u) for n, u in targets if n == args.only]
        if not targets:
            names = ", ".join(n for n, _ in cameras.get_cameras(args.targets))
            print(f"--only に指定できるのは: {names}")
            return 1

    if args.web:
        from video_kit import web

        return web.run(targets, roi_size=args.roi, port=args.port, open_browser=not args.no_open)

    width = args.width
    if width is None:
        width = SINGLE_WIDTH if len(targets) == 1 else DEFAULT_WIDTH
    return focus.run(targets, width=width, roi_size=args.roi)


def cmd_cameras(args: argparse.Namespace) -> int:
    # cameras.main は自前で argparse するので、残りの引数をそのまま渡す
    sys.argv = ["video-kit cameras", *args.rest]
    return cameras.main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-kit", description="RTSP カメラ向けの道具箱")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    focus = sub.add_parser("focus", help="ピント合わせ (鮮鋭度メーター付きライブビュー)")
    focus.add_argument(
        "targets",
        nargs="*",
        metavar="URL_OR_IP",
        help="RTSP URL / IP / デバイス番号 (0 = 内蔵カメラ)。省略時は環境変数",
    )
    focus.add_argument("--width", type=int, help="1 カメラあたりの表示幅")
    focus.add_argument("--roi", type=int, default=500, help="中央計測領域の一辺 [px]")
    focus.add_argument("--only", metavar="NAME", help="1 台だけ表示する (例: cam10)")
    focus.add_argument("--web", action="store_true", help="ブラウザに表示する (文字がくっきり)")
    focus.add_argument("--port", type=int, default=0, help="--web のポート。0 なら空きを自動で使う")
    focus.add_argument("--no-open", action="store_true", help="--web でブラウザを自動で開かない")
    focus.set_defaults(func=cmd_focus)

    cams = sub.add_parser("cameras", help="カメラを探して一覧表示", add_help=False)
    cams.add_argument("rest", nargs=argparse.REMAINDER)
    cams.set_defaults(func=cmd_cameras)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
