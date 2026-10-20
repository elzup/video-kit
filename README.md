# video-kit

RTSP カメラ向けの道具箱。

| コマンド | 何をするか |
|---|---|
| `video-kit focus` | ピント合わせ。ライブ映像に鮮鋭度メーターを重ねて表示する |
| `video-kit cameras` | 同じネットワークのカメラを探して IP / URL を表示する |

どの RTSP カメラでも使える。IP だけ渡したときは RouteCam (e-con Systems) 形式の URL で接続する。

---

## 1. インストール

必要なのは [uv](https://docs.astral.sh/uv/) だけ。Python は uv が自分で用意する。

```bash
brew install uv          # 未導入なら
uv tool install git+https://github.com/elzup/video-kit
```

これで `video-kit` コマンドが使えるようになる。

### 他の環境への影響

**無い。** uv は次の場所にしか書き込まない。

| 中身 | 場所 |
|---|---|
| video-kit 専用の環境 | `~/.local/share/uv/tools/video-kit/` |
| コマンド本体 (リンク) | `~/.local/bin/video-kit` |
| uv が入れた Python | `~/.local/share/uv/python/` |

- システム / Homebrew / pyenv の Python には触らない。
- それらを更新・削除しても video-kit は壊れない (uv 管理の Python だけを使う設定にしてある)。
- 他のプロジェクトの venv や Pipfile にも影響しない。

### 更新・削除

```bash
uv tool upgrade video-kit      # 最新にする
uv tool uninstall video-kit    # 跡形なく消す
```

### インストールせずに 1 回だけ試す

```bash
uvx --from git+https://github.com/elzup/video-kit video-kit focus
```

---

## 2. ピント合わせ `video-kit focus`

```bash
video-kit focus 192.0.2.10 192.0.2.11          # 2 台並べて表示
video-kit focus 192.0.2.10                     # IP を指定 (RouteCam 形式の URL になる)
video-kit focus rtsp://host:554/stream1       # URL を直接指定 (他機種はこちら)
video-kit focus 192.0.2.10 192.0.2.11 --only cam11   # 1 台だけ大きく表示
```

### 使い方

1. 起動するとカメラごとに映像と数値が出る
2. レンズをゆっくり回す
3. **数値が一番高くなった位置**で止める (下のバーはピーク値に対する今の値)

### 数値の目安 (中央領域)

| 値 | 表示 | 状態 |
|---|---|---|
| 100 未満 | `PINBOKE` | ピンボケ |
| 100〜300 | `SOFT` | 甘い |
| 300 以上 | `OK` | 実用域 |

絶対値は被写体で変わる。**「回して上がるか」を見る**のが本筋。

### キー操作

| キー | 動作 |
|---|---|
| `q` / `ESC` | 終了 (最後にピーク値を表示) |
| `r` | ピーク値をリセット |
| `c` | 魚眼円の検出表示を切り替え |
| `f` | 計測領域を 中央 / 全体 で切り替え |

### オプション

| オプション | 既定 | 意味 |
|---|---|---|
| `--width` | 760 (1 台なら 1100) | 1 カメラあたりの表示幅 |
| `--roi` | 500 | 中央計測領域の一辺 [px] |
| `--only NAME` | なし | 1 台だけ表示 (例: `cam11`) |

### 魚眼レンズの注意

ねじ込み式レンズはピントを回すと**円の大きさと中心も動く**。`c` で円を表示し、
ピントを合わせたら円の値 (`D=` と `c=`) を控えておく。

---

## 3. カメラを探す `video-kit cameras`

```bash
video-kit cameras               # ONVIF で探し、ダメならポートスキャン
video-kit cameras --scan-only   # ポートスキャンだけ
```

見つかった IP をそのまま `video-kit focus <IP>` に渡せる。

---

## 4. 接続先の決まり方

上から順に、最初に見つかったものを使う。

| 順位 | 指定方法 | 例 |
|---|---|---|
| 1 | コマンドの引数 | `video-kit focus 192.0.2.10` |
| 2 | 環境変数 `VIDEO_KIT_CAMERA_URLS` | `rtsp://a/1,rtsp://b/2` |
| 3 | 環境変数 `VIDEO_KIT_CAMERA_IPS` | `192.0.2.10,192.0.2.11` |

- どれも無ければ、接続先を指定するよう案内して終了する。
- IP だけ渡すと RouteCam 形式 `rtsp://<IP>:5005/routecam` になる。他の機種は URL を丸ごと渡す。

---

## 5. うまく映らないとき

| 症状 | 確認すること |
|---|---|
| `接続できません` | Mac がカメラと同じネットワークにいるか / カメラの電源 |
| カメラが見つからない | macOS の「ローカルネットワーク」許可 (システム設定 > プライバシーとセキュリティ) |
| 灰色の画面が続く | 回線が不安定。TCP で受信しているので通常は数秒で戻る |
| RouteCam が 554 で見つからない | RouteCam の RTSP は **5005** 番。554 は閉じている |

---

## 6. 開発

```bash
uv sync                    # .venv を作る (リポジトリ内だけ)
uv run video-kit focus     # 手元のコードで実行
uv run pytest              # テスト
uv run ruff check .        # lint
uv run ruff format .       # 整形
```

| ファイル | 役割 |
|---|---|
| `src/video_kit/cli.py` | コマンドの入口 |
| `src/video_kit/focus.py` | ピント合わせ画面と鮮鋭度 |
| `src/video_kit/cameras.py` | 接続先の決定とカメラ探索 |
| `src/video_kit/stream_reader.py` | 最新フレームだけを持つ RTSP 受信 |
| `src/video_kit/fisheye.py` | 魚眼円の検出 |
| `src/video_kit/capture_options.py` | OpenCV に渡す低遅延 RTSP 設定 |

