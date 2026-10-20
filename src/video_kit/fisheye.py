"""
魚眼円の検出

ピント調整で円の径・中心が大きく動くため (M12 等のねじ込み式レンズは
センサとの距離が変わり投影倍率が変わる)、ピント合わせ中に表示して確認する。
"""

import cv2
import numpy as np


def detect_circle(
    img: np.ndarray, dark_percentile: float = 5.0, margin: int = 6
) -> tuple[float, float, float]:
    """魚眼円の (中心x, 中心y, 半径) を推定する

    円の外は黒くケラれている前提で、明部の最大連結成分を取る。
    円が上下で切れていても、**水平方向の弦**から半径を復元できる
    (水平は 180° 全部が写っているため)。

    Args:
        img: 入力フレーム (BGR)
        dark_percentile: 黒レベルの推定に使うパーセンタイル
        margin: 黒レベルに足す余裕

    Returns:
        (cx, cy, radius) いずれも px
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    threshold = max(8, int(np.percentile(gray, dark_percentile)) + margin)
    mask = (gray > threshold).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count < 2:
        raise ValueError("魚眼円を検出できませんでした")
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (labels == idx).astype(np.uint8)

    # 円の境界点を集めて最小二乗フィットする。
    #
    # 重心を使ってはいけない: 円が上下非対称に切れていると重心が真の中心から
    # 大きくずれる (実機で 157 px)。
    # 最大弦の行を中心とする方法もダメ: 弦幅 2*sqrt(R^2-d^2) は中心付近で
    # 変化率がゼロに近いため、被写体のコントラスト次第で選ばれる行が揺れる
    # (実機のフレーム間で cy が 51 px ばらついた)。
    # 境界点を数百点集めて円フィットすれば、この両方を回避できる。
    height, width = mask.shape
    points = []
    for y in range(height):
        xs = np.where(mask[y] > 0)[0]
        if len(xs) < 2:
            continue
        left, right = int(xs.min()), int(xs.max())
        # フレーム端に接している側は円の境界ではないので捨てる
        if left > 0:
            points.append((left, y))
        if right < width - 1:
            points.append((right, y))

    if len(points) < 16:
        raise ValueError("円の境界点が不足しています")

    pts = np.asarray(points, dtype=np.float64)
    x, y = pts[:, 0], pts[:, 1]
    # x^2 + y^2 + D*x + E*y + F = 0  を線形最小二乗で解く
    A = np.column_stack([x, y, np.ones(len(pts))])
    b = -(x**2 + y**2)
    (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = -D / 2.0, -E / 2.0
    radius = float(np.sqrt(max(0.0, cx**2 + cy**2 - F)))

    # 妥当性チェック。RTSP のデコード破綻でグレー一色や壊れたフレームが
    # 来ることがあり、そのままフィットすると r=35 のような無意味な円が返る。
    if not (0.2 * min(height, width) <= radius <= 1.5 * max(height, width)):
        raise ValueError(f"半径が不合理です: {radius:.1f} px")
    if not (-0.5 * width <= cx <= 1.5 * width and -0.5 * height <= cy <= 1.5 * height):
        raise ValueError(f"中心が画面から外れすぎています: ({cx:.1f}, {cy:.1f})")

    return float(cx), float(cy), radius
