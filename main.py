from flask import Flask, request, render_template_string, send_file
import os
import shutil
import tempfile
import subprocess
import sys
import traceback
import html
import json
import re
import time
import imageio_ffmpeg
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>YouTube 360p MP4 Downloader</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f0f0f;
            color: white;
            text-align: center;
            margin: 0;
            padding: 20px;
        }

        h1 {
            font-size: 24px;
            margin-bottom: 10px;
        }

        input {
            width: 85%;
            max-width: 650px;
            padding: 13px;
            border-radius: 10px;
            border: none;
            margin-top: 20px;
            font-size: 16px;
        }

        button {
            padding: 12px 18px;
            border-radius: 10px;
            border: none;
            background: red;
            color: white;
            margin-top: 15px;
            cursor: pointer;
            font-size: 15px;
        }

        button:hover {
            opacity: 0.9;
        }

        .box {
            background: #1f1f1f;
            padding: 15px;
            margin: 20px auto 0;
            border-radius: 12px;
            max-width: 760px;
        }

        iframe {
            width: 100%;
            max-width: 650px;
            height: 340px;
            border: none;
            border-radius: 10px;
        }

        pre {
            white-space: pre-wrap;
            word-break: break-word;
            text-align: left;
            background: #111;
            padding: 10px;
            border-radius: 10px;
            color: #ddd;
            max-height: 500px;
            overflow-y: auto;
            font-size: 13px;
        }

        a {
            color: white;
            text-decoration: none;
        }

        .note {
            font-size: 14px;
            color: #cccccc;
            line-height: 1.6;
        }

        .warning {
            color: #ffcc66;
            font-weight: bold;
        }

        .ok {
            color: #99ff99;
            font-weight: bold;
        }

        .danger {
            color: #ff7777;
            font-weight: bold;
        }

        .info-grid {
            text-align: left;
            max-width: 650px;
            margin: 0 auto;
            line-height: 1.7;
        }

        .download-main {
            background: #e60000;
            font-size: 18px;
            padding: 15px 24px;
            width: 280px;
        }

        .sub-button {
            background: #444;
            margin-left: 4px;
            margin-right: 4px;
        }
    </style>
</head>

<body>

<h1>YouTube 360p MP4 Downloader</h1>

<p class="note">
    Render無料運用向けの安定版です。360pの音声付きMP4を優先して取得します。
</p>

<form method="POST">
    <input
        type="text"
        name="input"
        placeholder="YouTube URL / Shorts URL / 動画ID を貼ってください">

    <br>

    <button type="submit">
        表示
    </button>
</form>

{% if error %}
<div class="box">
    <p class="danger">{{ error }}</p>
</div>
{% endif %}

{% if video_id %}
<div class="box">

    <h2>動画</h2>

    <iframe
        src="https://www.youtube.com/embed/{{ video_id }}"
        allowfullscreen>
    </iframe>

    {% if analysis %}
    <div class="box">
        <h3>動画情報</h3>

        {% if analysis.ok %}
        <div class="info-grid">
            <p><strong>タイトル：</strong>{{ analysis.title }}</p>
            <p><strong>長さ：</strong>{{ analysis.duration_text }}</p>
            <p><strong>Render上で見えている画質：</strong>{{ analysis.qualities_text }}</p>
            <p class="ok"><strong>おすすめ：</strong>360p安定版</p>

            {% if analysis.warning %}
            <p class="warning">{{ analysis.warning }}</p>
            {% endif %}

            <p class="note">{{ analysis.message }}</p>
        </div>
        {% else %}
        <p class="danger">動画情報の解析に失敗しました</p>
        <p>{{ analysis.reason }}</p>

        {% if analysis.cookie_help %}
        <a href="/cookie-help">
            <button class="sub-button">
                Cookie更新方法を見る
            </button>
        </a>
        {% endif %}
        {% endif %}
    </div>
    {% endif %}

    <br>

    <a href="/confirm?v={{ video_id }}">
        <button class="download-main">
            ダウンロード確認へ
        </button>
    </a>

    <br>

    <a href="/warmup?v={{ video_id }}">
        <button class="sub-button">
            事前準備
        </button>
    </a>

    <a href="/formats-check?v={{ video_id }}">
        <button class="sub-button">
            形式チェック
        </button>
    </a>

    <a href="/runtime-check">
        <button class="sub-button">
            Runtime確認
        </button>
    </a>

    <a href="/cookie-check">
        <button class="sub-button">
            Cookie確認
        </button>
    </a>

    <a href="/cookie-help">
        <button class="sub-button">
            Cookie更新方法
        </button>
    </a>

    <p class="note">
        初回だけ失敗する場合は「事前準備」を一度押してから、もう一度ダウンロードしてください。
    </p>

</div>
{% endif %}

</body>
</html>
"""


CONFIRM_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ダウンロード確認</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f0f0f;
            color: white;
            text-align: center;
            margin: 0;
            padding: 20px;
        }

        .box {
            background: #1f1f1f;
            padding: 18px;
            margin: 20px auto 0;
            border-radius: 12px;
            max-width: 760px;
        }

        button {
            padding: 14px 22px;
            border-radius: 10px;
            border: none;
            background: red;
            color: white;
            margin-top: 15px;
            cursor: pointer;
            font-size: 16px;
        }

        .sub-button {
            background: #444;
        }

        iframe {
            width: 100%;
            max-width: 650px;
            height: 340px;
            border: none;
            border-radius: 10px;
        }

        a {
            color: white;
            text-decoration: none;
        }

        .note {
            font-size: 14px;
            color: #cccccc;
            line-height: 1.6;
        }

        .warning {
            color: #ffcc66;
            font-weight: bold;
        }

        .ok {
            color: #99ff99;
            font-weight: bold;
        }

        .danger {
            color: #ff7777;
            font-weight: bold;
        }

        .info-grid {
            text-align: left;
            max-width: 650px;
            margin: 0 auto;
            line-height: 1.7;
        }
    </style>

    <script>
        function showDownloading(button) {
            button.innerText = "ダウンロード処理中...";
            button.disabled = true;
            return true;
        }
    </script>
</head>

<body>

<h1>ダウンロード確認</h1>

<div class="box">

    <iframe
        src="https://www.youtube.com/embed/{{ video_id }}"
        allowfullscreen>
    </iframe>

    <div class="box">
        <h3>この動画を360p MP4で保存します</h3>

        {% if analysis and analysis.ok %}
        <div class="info-grid">
            <p><strong>タイトル：</strong>{{ analysis.title }}</p>
            <p><strong>長さ：</strong>{{ analysis.duration_text }}</p>
            <p><strong>Render上で見えている画質：</strong>{{ analysis.qualities_text }}</p>

            {% if analysis.warning %}
            <p class="warning">{{ analysis.warning }}</p>
            {% endif %}

            <p class="ok">保存形式：360p MP4</p>
            <p class="note">{{ analysis.message }}</p>
        </div>
        {% else %}
        <p class="warning">
            動画情報の詳細解析はできませんでしたが、360p MP4で取得を試します。
        </p>
        {% endif %}
    </div>

    <a href="/download?v={{ video_id }}" onclick="return showDownloading(this.querySelector('button'));">
        <button>
            この内容でダウンロードする
        </button>
    </a>

    <br>

    <a href="/">
        <button class="sub-button">
            戻る
        </button>
    </a>

    <p class="note">
        処理中は画面が止まったように見えることがあります。完了するとMP4保存画面が開きます。
    </p>

</div>

</body>
</html>
"""


COOKIE_HELP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Cookie更新方法</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0f0f0f;
            color: white;
            margin: 0;
            padding: 20px;
            line-height: 1.7;
        }

        .box {
            background: #1f1f1f;
            padding: 18px;
            margin: 20px auto 0;
            border-radius: 12px;
            max-width: 760px;
        }

        code, pre {
            background: #111;
            color: #ddd;
            padding: 8px;
            border-radius: 8px;
            display: block;
            white-space: pre-wrap;
            word-break: break-word;
        }

        button {
            padding: 12px 18px;
            border-radius: 10px;
            border: none;
            background: red;
            color: white;
            margin-top: 15px;
            cursor: pointer;
        }

        a {
            color: white;
            text-decoration: none;
        }

        .warning {
            color: #ffcc66;
            font-weight: bold;
        }
    </style>
</head>

<body>

<div class="box">
    <h1>Cookie更新方法</h1>

    <p class="warning">
        cookies.txt はログイン状態の鍵のようなものです。GitHubや他人に見える場所には絶対に置かないでください。
    </p>

    <h3>エラーの目安</h3>
    <p>以下が出たら、cookies.txtの更新が必要な可能性が高いです。</p>

    <pre>Sign in to confirm you’re not a bot</pre>

    <h3>更新手順</h3>

    <ol>
        <li>ChromeでYouTubeにログインする</li>
        <li>シークレットウィンドウを使う場合は、Cookie出力用拡張機能をシークレットで許可する</li>
        <li>YouTubeにログインした同じタブで以下を開く</li>
    </ol>

    <pre>https://www.youtube.com/robots.txt</pre>

    <ol start="4">
        <li>Cookie出力拡張機能で cookies.txt をExportする</li>
        <li>RenderのWeb Serviceを開く</li>
        <li>Environment → Secret Files を開く</li>
        <li>Filenameを <strong>cookies.txt</strong> にする</li>
        <li>Contentsに新しいcookies.txtの中身を全部貼る</li>
        <li>Manual Deployする</li>
    </ol>

    <h3>Secret File名</h3>

    <pre>cookies.txt</pre>

    <p>名前が <code>cookie.txt</code> や <code>Cookies.txt</code> だと動きません。</p>

    <a href="/cookie-check">
        <button>Cookie確認へ</button>
    </a>

    <a href="/">
        <button>トップへ戻る</button>
    </a>
</div>

</body>
</html>
"""


@app.errorhandler(Exception)
def handle_exception(e):
    error_text = traceback.format_exc()
    return f"""
    <h2>アプリ内部エラー</h2>
    <p>以下をコピーして確認してください。</p>
    <pre>{html.escape(error_text)}</pre>
    """, 500


def get_video_id(text):
    if not text:
        return None

    text = text.strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text

    try:
        parsed = urlparse(text)

        if "youtube.com" in parsed.netloc:
            if parsed.path == "/watch":
                query = parse_qs(parsed.query)
                return query.get("v", [None])[0]

            if parsed.path.startswith("/shorts/"):
                return parsed.path.split("/shorts/")[1].split("/")[0]

            if parsed.path.startswith("/embed/"):
                return parsed.path.split("/embed/")[1].split("/")[0]

        if "youtu.be" in parsed.netloc:
            return parsed.path.strip("/").split("/")[0]

    except Exception:
        return None

    return None


def prepare_cookie():
    render_cookie = "/etc/secrets/cookies.txt"
    local_cookie = "cookies.txt"
    cookie_path = f"/tmp/cookies_runtime_{os.getpid()}.txt"

    if os.path.exists(render_cookie):
        source_cookie = render_cookie
    elif os.path.exists(local_cookie):
        source_cookie = local_cookie
    else:
        return None, "cookies.txt が見つかりません。RenderではSecret File名を cookies.txt にしてください。"

    try:
        shutil.copy(source_cookie, cookie_path)
    except Exception as e:
        return None, f"cookieコピー失敗: {str(e)}"

    return cookie_path, None


def get_ffmpeg_path():
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def get_deno_path():
    candidates = [
        "/opt/render/project/src/.deno/bin/deno",
        "/opt/render/project/.deno/bin/deno",
        "/opt/render/.deno/bin/deno",
        os.path.expanduser("~/.deno/bin/deno"),
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    found = shutil.which("deno")

    if found:
        return found

    return "deno"


def run_command(cmd, timeout=180):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout
    )

    return result.returncode, result.stdout, result.stderr


def base_ytdlp_cmd(cookie_path=None):
    deno_path = get_deno_path()

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",

        "--no-playlist",

        "--force-ipv4",

        "--js-runtimes",
        f"deno:{deno_path}",

        "--remote-components",
        "ejs:npm",

        "--user-agent",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),

        "--referer",
        "https://www.youtube.com/",
    ]

    if cookie_path:
        cmd += [
            "--cookies",
            cookie_path
        ]

    return cmd


def add_client_args(cmd, client_name):
    if client_name == "default":
        return cmd

    return cmd + [
        "--extractor-args",
        f"youtube:player_client={client_name}"
    ]


def seconds_to_text(seconds):
    if seconds is None:
        return "不明"

    try:
        seconds = int(seconds)
    except Exception:
        return "不明"

    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h > 0:
        return f"{h}時間{m}分{s}秒"

    if m > 0:
        return f"{m}分{s}秒"

    return f"{s}秒"


def explain_error(text):
    text = text or ""
    lower = text.lower()

    if "sign in to confirm" in lower or "not a bot" in lower:
        return "YouTube側にbot判定されています。cookies.txtが切れている可能性があります。cookies.txtを作り直してRenderのSecret Fileに入れ直してください。"

    if "requested format is not available" in lower:
        return "指定した形式がこの動画では取得できません。形式チェックで 18 mp4 が出ているか確認してください。"

    if "only images are available" in lower or ("storyboard" in lower and "mp4" not in lower):
        return "動画本体ではなく、シークバー用のプレビュー画像だけが見えています。Deno、cookies、RenderのIP制限のどれかが原因の可能性があります。"

    if "no supported javascript runtime" in lower or ("deno" in lower and "no such file" in lower):
        return "Denoが正しく動いていません。Build CommandでDenoが入っているか、runtime-checkを確認してください。"

    if "ffmpeg" in lower:
        return "ffmpeg関連のエラーです。ffmpeg-checkを確認してください。"

    if "timeout" in lower or "timed out" in lower or "タイムアウト" in text:
        return "処理が時間切れになりました。動画が長い、またはRender側の処理制限に近い可能性があります。短い動画から試してください。"

    if "http error 403" in lower or "forbidden" in lower:
        return "YouTube側にアクセスを拒否されています。cookies.txtの更新、または時間を置いて再試行してください。"

    if "read-only file system" in lower:
        return "RenderのSecret Fileを直接書き換えようとして失敗しています。cookies.txtは/tmpにコピーして使う必要があります。"

    if "file not found" in lower or "not found" in lower:
        return "生成ファイルの取得に失敗しています。もう一度試すか、事前準備を押してから再試行してください。"

    return "原因を特定できませんでした。形式チェック、Cookie確認、Runtime確認の順で確認してください。"


def safe_filename(name):
    if not name:
        return "video.mp4"

    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = name.strip()

    if not name:
        name = "video"

    if not name.lower().endswith(".mp4"):
        name += ".mp4"

    return name[:140]


def get_json_from_stdout(stdout):
    stdout = stdout.strip()

    if not stdout:
        return None

    try:
        return json.loads(stdout)
    except Exception:
        pass

    start = stdout.find("{")
    end = stdout.rfind("}")

    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(stdout[start:end + 1])
        except Exception:
            return None

    return None


def analyze_formats(formats):
    heights = set()
    has_18 = False

    for f in formats:
        vcodec = f.get("vcodec")
        height = f.get("height")
        format_id = str(f.get("format_id", ""))

        if format_id == "18":
            has_18 = True
            heights.add(360)

        if vcodec and vcodec != "none" and height:
            try:
                heights.add(int(height))
            except Exception:
                pass

    qualities = []

    if any(h >= 1080 for h in heights):
        qualities.append(1080)

    if any(h >= 720 for h in heights):
        qualities.append(720)

    if any(h >= 480 for h in heights):
        qualities.append(480)

    if any(h >= 360 for h in heights) or has_18:
        qualities.append(360)

    qualities = sorted(list(set(qualities)), reverse=True)

    return qualities, has_18


def analyze_video(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return {
            "ok": False,
            "reason": cookie_error,
            "cookie_help": True
        }

    clients = [
        {"name": "web", "cookie": True},
        {"name": "default", "cookie": True},
        {"name": "ios", "cookie": True},
        {"name": "android", "cookie": True},
    ]

    last_output = ""

    for item in clients:
        client = item["name"]
        use_cookie = item["cookie"]

        cmd = base_ytdlp_cmd(cookie_path if use_cookie else None)
        cmd = add_client_args(cmd, client)

        cmd += [
            "-J",
            url
        ]

        try:
            code, stdout, stderr = run_command(cmd, timeout=180)
            last_output = stdout + "\n" + stderr

            if code != 0:
                continue

            info = get_json_from_stdout(stdout)

            if not info:
                continue

            title = info.get("title") or "不明"
            duration = info.get("duration")
            formats = info.get("formats", [])

            qualities, has_18 = analyze_formats(formats)

            if not qualities:
                continue

            warning = ""
            message = "360pの音声付きMP4を優先して取得します。"

            if duration and duration >= 1800:
                warning = "この動画は30分以上あります。Renderでは長い動画が失敗しやすいので注意してください。"
            elif duration and duration >= 600:
                warning = "この動画は10分以上あります。失敗した場合は時間を置いて再試行してください。"

            if not has_18:
                warning = "Render上で安定版の18番MP4が見えていません。ダウンロードに失敗する可能性があります。"
                message = "形式チェックで18 mp4が出ているか確認してください。"

            qualities_text = " / ".join([f"{q}p" for q in qualities])

            return {
                "ok": True,
                "title": title,
                "duration": duration,
                "duration_text": seconds_to_text(duration),
                "qualities": qualities,
                "qualities_text": qualities_text,
                "warning": warning,
                "message": message,
                "client": client
            }

        except Exception as e:
            last_output += "\n" + str(e)
            continue

    reason = explain_error(last_output)

    return {
        "ok": False,
        "reason": reason,
        "cookie_help": "cookies.txt" in reason or "bot判定" in reason
    }


def find_mp4_file(folder):
    found = []

    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(".mp4"):
                full_path = os.path.join(root, file)

                if os.path.getsize(full_path) > 0:
                    found.append(full_path)

    if not found:
        return None

    return max(found, key=os.path.getctime)


def find_any_file(folder):
    found = []

    for root, dirs, files in os.walk(folder):
        for file in files:
            full_path = os.path.join(root, file)

            if os.path.getsize(full_path) > 0:
                found.append(full_path)

    if not found:
        return None

    return max(found, key=os.path.getctime)


@app.route("/", methods=["GET", "POST"])
def home():
    video_id = None
    error = None
    analysis = None

    if request.method == "POST":
        text = request.form.get("input", "").strip()
        video_id = get_video_id(text)

        if not video_id:
            error = "YouTube URLを入力してください"
        else:
            analysis = analyze_video(video_id)

    return render_template_string(
        HTML,
        video_id=video_id,
        error=error,
        analysis=analysis
    )


@app.route("/confirm")
def confirm():
    video_id = request.args.get("v")

    if not video_id:
        return "動画IDがありません", 400

    analysis = analyze_video(video_id)

    return render_template_string(
        CONFIRM_HTML,
        video_id=video_id,
        analysis=analysis
    )


@app.route("/download")
def download():
    video_id = request.args.get("v")

    if not video_id:
        return "動画IDがありません", 400

    url = f"https://www.youtube.com/watch?v={video_id}"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return f"""
        <h2>DL失敗</h2>
        <p>{html.escape(cookie_error)}</p>
        <p>{html.escape(explain_error(cookie_error))}</p>
        <a href="/cookie-help"><button>Cookie更新方法を見る</button></a>
        """, 500

    ffmpeg_path = get_ffmpeg_path()

    if not ffmpeg_path:
        return """
        <h2>DL失敗</h2>
        <p>ffmpegが取得できません</p>
        <p>ffmpeg-checkを確認してください。</p>
        <a href="/ffmpeg-check"><button>ffmpeg確認</button></a>
        """, 500

    temp_dir = tempfile.mkdtemp(prefix="yt_")
    output_path = os.path.join(temp_dir, "%(title).80s [%(id)s].%(ext)s")

    clients = [
        {"name": "web", "cookie": True},
        {"name": "default", "cookie": True},
        {"name": "ios", "cookie": True},
        {"name": "android", "cookie": True},
    ]

    format_patterns = [
        "18",
        "18/best[ext=mp4][height<=360]/best[height<=360]",
        "best[ext=mp4]/best",
    ]

    errors = []

    for item in clients:
        client = item["name"]
        use_cookie = item["cookie"]

        for fmt in format_patterns:
            cmd = base_ytdlp_cmd(cookie_path if use_cookie else None)
            cmd = add_client_args(cmd, client)

            cmd += [
                "--ffmpeg-location",
                ffmpeg_path,

                "-f",
                fmt,

                "--merge-output-format",
                "mp4",

                "--recode-video",
                "mp4",

                "-o",
                output_path,

                url
            ]

            try:
                code, stdout, stderr = run_command(cmd, timeout=420)

                output = stdout + "\n" + stderr

                if code == 0:
                    time.sleep(1)

                    mp4_file = find_mp4_file(temp_dir)

                    if mp4_file and os.path.exists(mp4_file):
                        filename = os.path.basename(mp4_file)
                        filename = safe_filename(filename)

                        return send_file(
                            mp4_file,
                            as_attachment=True,
                            download_name=filename,
                            conditional=False,
                            max_age=0
                        )

                    any_file = find_any_file(temp_dir)

                    if any_file:
                        errors.append(
                            f"client={client}, cookie={use_cookie}, format={fmt}: mp4なし。生成ファイル: {os.path.basename(any_file)}"
                        )
                    else:
                        errors.append(
                            f"client={client}, cookie={use_cookie}, format={fmt}: 成功扱いだがファイルなし"
                        )

                else:
                    errors.append(
                        f"""
client={client}
cookie={use_cookie}
format={fmt}
return code={code}
STDOUT:
{stdout}
STDERR:
{stderr}
"""
                    )

            except subprocess.TimeoutExpired:
                errors.append(
                    f"client={client}, cookie={use_cookie}, format={fmt}: タイムアウト"
                )

            except Exception as e:
                errors.append(
                    f"client={client}, cookie={use_cookie}, format={fmt}: 例外 {str(e)}"
                )

    error_output = "\n".join(errors)

    if len(error_output) > 60000:
        error_output = error_output[:60000] + "\n\n--- エラー出力が長すぎるため省略 ---"

    reason = explain_error(error_output)

    cookie_button = ""

    if "cookies" in reason or "bot判定" in reason:
        cookie_button = '<a href="/cookie-help"><button>Cookie更新方法を見る</button></a>'

    return f"""
    <h2>DL失敗</h2>
    <p><strong>日本語の原因候補：</strong>{html.escape(reason)}</p>
    <p>360p安定版でも失敗しました。Cookie確認・Runtime確認・形式チェックを見てください。</p>

    <a href="/confirm?v={html.escape(video_id)}"><button>もう一度試す</button></a>
    <a href="/formats-check?v={html.escape(video_id)}"><button>形式チェック</button></a>
    <a href="/runtime-check"><button>Runtime確認</button></a>
    <a href="/cookie-check"><button>Cookie確認</button></a>
    {cookie_button}

    <pre>{html.escape(error_output)}</pre>
    """, 500


@app.route("/warmup")
def warmup():
    video_id = request.args.get("v")

    if not video_id:
        return "動画IDがありません", 400

    url = f"https://www.youtube.com/watch?v={video_id}"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return cookie_error, 500

    cmd = base_ytdlp_cmd(cookie_path)
    cmd = add_client_args(cmd, "web")
    cmd += ["-F", url]

    try:
        code, stdout, stderr = run_command(cmd, timeout=180)
        output = stdout + "\n" + stderr

        return f"""
        <h2>事前準備 完了</h2>
        <p>return code: {code}</p>
        <p>このあと戻って、360p MP4ダウンロードを押してください。</p>
        <a href="/confirm?v={html.escape(video_id)}"><button>確認画面へ戻る</button></a>
        <pre>{html.escape(output[:30000])}</pre>
        """

    except Exception as e:
        return f"事前準備エラー: {html.escape(str(e))}", 500


@app.route("/cookie-help")
def cookie_help():
    return render_template_string(COOKIE_HELP_HTML)


@app.route("/health")
def health():
    return "OK"


@app.route("/runtime-check")
def runtime_check():
    outputs = []

    commands = [
        ["python version", [sys.executable, "--version"]],
        ["yt-dlp version", [sys.executable, "-m", "yt_dlp", "--version"]],
        ["deno version", [get_deno_path(), "--version"]],
    ]

    for title, cmd in commands:
        try:
            code, stdout, stderr = run_command(cmd, timeout=60)

            outputs.append(
                f"""
==============================
{title}
return code: {code}
==============================
STDOUT:
{stdout}

STDERR:
{stderr}
"""
            )

        except Exception as e:
            outputs.append(
                f"""
==============================
{title}
ERROR
==============================
{str(e)}
"""
            )

    ffmpeg_path = get_ffmpeg_path()

    outputs.append(
        f"""
==============================
ffmpeg
==============================
{ffmpeg_path}
exists: {os.path.exists(ffmpeg_path) if ffmpeg_path else False}

==============================
deno path used
==============================
{get_deno_path()}
"""
    )

    return f"""
    <h2>Runtime Check</h2>
    <pre>{html.escape(''.join(outputs))}</pre>
    """


@app.route("/cookie-check")
def cookie_check():
    render_cookie = "/etc/secrets/cookies.txt"
    local_cookie = "cookies.txt"

    if os.path.exists(render_cookie):
        cookie_file = render_cookie
        location = "Render Secret File"
    elif os.path.exists(local_cookie):
        cookie_file = local_cookie
        location = "Local cookies.txt"
    else:
        return """
        <h2>Cookie Check</h2>
        <p>NG: cookies.txt が存在しません</p>
        <a href="/cookie-help"><button>Cookie更新方法を見る</button></a>
        """

    size = os.path.getsize(cookie_file)

    with open(cookie_file, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    has_youtube = "youtube.com" in text
    has_google = "google.com" in text
    has_sid = "SID" in text or "__Secure" in text
    starts_ok = "# Netscape HTTP Cookie File" in text[:200]

    return f"""
    <h2>Cookie Check</h2>
    <p>location: {location}</p>
    <p>file: OK</p>
    <p>size: {size} bytes</p>
    <p>Netscape形式: {starts_ok}</p>
    <p>youtube.com cookieあり: {has_youtube}</p>
    <p>google.com cookieあり: {has_google}</p>
    <p>ログイン系cookieらしきものあり: {has_sid}</p>

    <hr>

    <p>bot判定エラーが出る場合は、cookies.txtを作り直してください。</p>
    <a href="/cookie-help"><button>Cookie更新方法を見る</button></a>
    """


@app.route("/ffmpeg-check")
def ffmpeg_check():
    ffmpeg_path = get_ffmpeg_path()

    if not ffmpeg_path:
        return "ffmpeg NG"

    if os.path.exists(ffmpeg_path):
        return f"ffmpeg OK: {ffmpeg_path}"

    return "ffmpeg NG: ファイルが存在しません"


@app.route("/formats-check")
def formats_check():
    video_id = request.args.get("v")
    url = request.args.get("url")

    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"

    if not url:
        return "URLまたは動画IDがありません"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return cookie_error

    clients = [
        {"name": "web", "cookie": True},
        {"name": "default", "cookie": True},
        {"name": "ios", "cookie": True},
        {"name": "android", "cookie": True},
    ]

    outputs = []

    for item in clients:
        client = item["name"]
        use_cookie = item["cookie"]

        cmd = base_ytdlp_cmd(cookie_path if use_cookie else None)
        cmd = add_client_args(cmd, client)

        cmd += ["-F", url]

        try:
            code, stdout, stderr = run_command(cmd, timeout=180)
            output = stdout + "\n" + stderr

            outputs.append(
                f"""
==============================
CLIENT: {client}
COOKIE: {use_cookie}
RETURN CODE: {code}
==============================
OUTPUT:
{output}
"""
            )

            if " 18 " in output or " mp4 " in output:
                break

        except subprocess.TimeoutExpired:
            outputs.append(
                f"""
==============================
CLIENT: {client}
TIMEOUT
==============================
"""
            )

        except Exception as e:
            outputs.append(
                f"""
==============================
CLIENT: {client}
ERROR
==============================
{str(e)}
"""
            )

    final_output = "".join(outputs)

    if len(final_output) > 60000:
        final_output = final_output[:60000] + "\n\n--- 出力が長すぎるため省略 ---"

    return f"""
    <h2>Formats Check</h2>
    <pre>{html.escape(final_output)}</pre>
    """


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
