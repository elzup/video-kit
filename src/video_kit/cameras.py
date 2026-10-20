"""
カメラの所在を決める + ONVIF / ポートスキャンによる自動発見

接続先の優先順位:
    1. コマンドライン引数の URL / IP
    2. 環境変数 VIDEO_KIT_CAMERA_URLS (RTSP URL を直接、カンマ区切り)
    3. 環境変数 VIDEO_KIT_CAMERA_IPS  (例: "192.0.2.10,192.0.2.11")

    どれも無ければ空を返す (現場の IP をコードに持たないため)。

IP が分からないときの手順:

    video-kit cameras                        # 探して一覧表示
    export VIDEO_KIT_CAMERA_IPS=<出てきた IP をカンマ区切り>

IP だけ渡したときの URL は RouteCam 形式 (rtsp://<ip>:5005/routecam) になる。
他の機種は URL を丸ごと渡す。

なぜポートスキャンで見つからないか:
    このカメラ (e-con Systems RouteCam) は **RTSP を 554 ではなく 5005**
    で提供しており、554 は閉じている。`nmap -p554` 相当では発見できない。
    ONVIF の WS-Discovery (UDP マルチキャスト 239.255.255.250:3702) を使う。
"""

import os
import re
import socket
import uuid

RTSP_PORT = 5005
RTSP_PATH = "routecam"
ONVIF_PORT = 8000

MCAST_GRP = "239.255.255.250"
MCAST_PORT = 3702

_PROBE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header>
<w:MessageID>uuid:{msgid}</w:MessageID>
<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
</e:Header>
<e:Body><d:Probe><d:Types>{types}</d:Types></d:Probe></e:Body>
</e:Envelope>"""


def rtsp_url(ip: str) -> str:
    return f"rtsp://{ip}:{RTSP_PORT}/{RTSP_PATH}"


def onvif_url(ip: str) -> str:
    return f"http://{ip}:{ONVIF_PORT}/onvif/device_service"


def camera_name(ip: str) -> str:
    """IP の最終オクテットから短い名前を作る (192.0.2.10 -> cam10)"""
    return "cam" + ip.rsplit(".", 1)[-1]


def _split(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def from_targets(targets: list[str]) -> list[tuple[str, str]]:
    """URL / IP / デバイス番号の並びを [(名前, 接続先), ...] にする

    数字だけならローカルのカメラ (0 = Mac 内蔵カメラ等) として扱う。
    """
    cameras = []
    for i, target in enumerate(targets):
        if target.isdigit():
            cameras.append((f"dev{target}", target))
        elif "://" in target:
            cameras.append((f"cam{i + 1}", target))
        else:
            cameras.append((camera_name(target), rtsp_url(target)))
    return cameras


def get_cameras(targets: list[str] | None = None) -> list[tuple[str, str]]:
    """[(名前, RTSP URL), ...] を返す。優先順位はモジュール先頭を参照"""
    if targets:
        return from_targets(targets)

    urls = os.getenv("VIDEO_KIT_CAMERA_URLS")
    if urls:
        return [(f"cam{i + 1}", u) for i, u in enumerate(_split(urls))]

    ips = os.getenv("VIDEO_KIT_CAMERA_IPS")
    if ips:
        return [(camera_name(ip), rtsp_url(ip)) for ip in _split(ips)]
    return []


def describe_source() -> str:
    """get_cameras() が何を元にしたかを返す (表示用)"""
    for name in ("VIDEO_KIT_CAMERA_URLS", "VIDEO_KIT_CAMERA_IPS"):
        if os.getenv(name):
            return name
    return "未設定"


def local_ip() -> str:
    """既定経路に使われるローカル IP を返す

    macOS では **マルチキャストの送出元を 0.0.0.0 にすると届かない**ため、
    実インタフェースの IP を明示する必要がある。
    UDP ソケットを connect するだけでパケットは飛ばない。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        sock.close()


def discover(timeout: float = 6.0, iface_ip: str | None = None) -> list[dict]:
    """ONVIF WS-Discovery でカメラを探す

    Args:
        iface_ip: 送出元インタフェースの IP。None なら自動検出

    Returns:
        [{"ip": ..., "xaddrs": [...], "name": ...}, ...]
    """
    if iface_ip is None:
        iface_ip = local_ip()

    found: dict = {}
    for types in ("dn:NetworkVideoTransmitter", "d:NetworkVideoTransmitter"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
        try:
            sock.bind((iface_ip, 0))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
            if iface_ip != "0.0.0.0":
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_MULTICAST_IF,
                    socket.inet_aton(iface_ip),
                )
            sock.settimeout(timeout)
            message = _PROBE.format(msgid=uuid.uuid4(), types=types).encode()
            for _ in range(3):  # 取りこぼし対策
                sock.sendto(message, (MCAST_GRP, MCAST_PORT))
            while True:
                try:
                    data, addr = sock.recvfrom(65535)
                except TimeoutError:
                    break
                text = data.decode("utf-8", "replace")
                entry = found.setdefault(addr[0], {"ip": addr[0], "xaddrs": set(), "name": ""})
                for chunk in re.findall(r"<[^>]*XAddrs[^>]*>([^<]+)<", text):
                    entry["xaddrs"].update(chunk.split())
                for scope in re.findall(r"<[^>]*Scopes[^>]*>([^<]+)<", text):
                    match = re.search(r"onvif://www\.onvif\.org/name/(\S+)", scope)
                    if match:
                        entry["name"] = match.group(1)
        finally:
            sock.close()

    return [
        {"ip": v["ip"], "xaddrs": sorted(v["xaddrs"]), "name": v["name"]}
        for v in sorted(found.values(), key=lambda d: d["ip"])
    ]


def scan_subnet(
    port: int = RTSP_PORT, timeout: float = 1.0, subnet: str | None = None
) -> list[str]:
    """サブネットを総当たりして指定ポートが開いているホストを返す

    ONVIF のマルチキャストは環境によって届かない (macOS のローカル
    ネットワーク許可、VLAN、AP のマルチキャスト抑制など)。RTSP のポートが
    分かっているならこちらの方が確実。
    """
    from concurrent.futures import ThreadPoolExecutor

    if subnet is None:
        base = local_ip()
        if base == "0.0.0.0":
            return []
        subnet = base.rsplit(".", 1)[0]

    def probe(host: str) -> str | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            return host if sock.connect_ex((host, port)) == 0 else None
        except OSError:
            return None
        finally:
            sock.close()

    hosts = [f"{subnet}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=128) as pool:
        results = list(pool.map(probe, hosts))
    return [h for h in results if h]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="カメラを探して設定用の行を出力する "
        "(ONVIF マルチキャスト → 届かなければポートスキャン)"
    )
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--iface", default=None, help="送出元インタフェースの IP")
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="ONVIF を試さずポートスキャンだけ行う",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="ONVIF が空振りしてもポートスキャンしない",
    )
    args = parser.parse_args()

    print("現在の設定:")
    for name, url in get_cameras():
        print(f"  {name}: {url}")
    print(f"  (取得元: {describe_source()})")

    found_ips: list[str] = []

    if not args.scan_only:
        print(f"\nONVIF で探索中 ({args.timeout:.0f} 秒)...")
        devices = discover(timeout=args.timeout, iface_ip=args.iface)
        if devices:
            print(f"  {len(devices)} 台:")
            for device in devices:
                label = f" [{device['name']}]" if device["name"] else ""
                print(f"    {device['ip']}{label}")
                print(f"      RTSP : {rtsp_url(device['ip'])}")
                for xaddr in device["xaddrs"]:
                    print(f"      ONVIF: {xaddr}")
            found_ips = [d["ip"] for d in devices]
        else:
            print("  応答なし。")

    if not found_ips and not args.no_scan:
        base = local_ip()
        subnet = base.rsplit(".", 1)[0] if base != "0.0.0.0" else "?"
        print(f"\nポート {RTSP_PORT} をスキャン中 ({subnet}.0/24)...")
        found_ips = scan_subnet()
        if found_ips:
            print(f"  {len(found_ips)} 台:")
            for ip in found_ips:
                print(f"    {ip}  ->  {rtsp_url(ip)}")
        else:
            print("  見つかりませんでした。")

    if not found_ips:
        print("\n確認してください:")
        print(f"  - この PC ({local_ip()}) がカメラと同じセグメントにいるか")
        print("  - カメラの電源が入っているか")
        print("  - macOS のローカルネットワーク許可")
        print("    (システム設定 > プライバシーとセキュリティ > ローカルネットワーク)")
        print(
            f"  - RTSP のポートが {RTSP_PORT} のままか "
            f"(違うなら --scan-only の前に RTSP_PORT を直す)"
        )
        return 1

    ips = ",".join(found_ips)
    print("\nこのセッションで使うには:")
    print(f"  export VIDEO_KIT_CAMERA_IPS={ips}")
    print("\nまたは直接渡す:")
    print(f"  video-kit focus {' '.join(found_ips)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
