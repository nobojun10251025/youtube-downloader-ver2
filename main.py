from flask import Flask, request, render_template_string, send_file
import os
import shutil
import tempfile
import subprocess
import sys
import traceback
import html
import time
import imageio_ffmpeg
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>YouTube MP4 Downloader</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        body {
            font-family: Arial;
            background: #0f0f0f;
            color: white;
            text-align: center;
            margin: 0;
            padding: 20px;
        }

        input {
            width: 85%;
            padding: 12px;
            border-radius: 10px;
            border: none;
            margin-top: 20px;
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

        .box {
            background: #1f1f1f;
            padding: 15px;
            margin-top: 20px;
            border-radius: 12px;
        }

        iframe {
            width: 100%;
            max-width: 600px;
            height: 320px;
            border: none;
        }

        pre {
            white-space: pre-wrap;
            word-break: break-word;
            text-align: left;
            background: #111;
            padding: 10px;
            border-radius: 10px;
            color: #ddd;
            max-height: 650px;
            overflow-y: auto;
        }

        a {
            color: white;
            text-decoration: none;
        }

        .note {
            font-size: 14px;
            color: #cccccc;
        }

        .quality-buttons a button {
            width: 150px;
            margin: 6px;
        }
    </style>
</head>

<body>

<h1>YouTube MP4 Downloader</h1>

<form method="POST">
    <input
        type="text"
        name="input"
        placeholder="YouTube URLを貼ってください">

    <br>

    <button type="submit">
        表示
    </button>
</form>

{% if error %}
<div class="box">
    <p>{{ error }}</p>
</div>
{% endif %}

{% if video_id %}
<div class="box">

    <h2>動画</h2>

    <iframe
        src="https://www.youtube.com/embed/{{ video_id }}"
        allowfullscreen>
    </iframe>

    <br>

    <div class="quality-buttons">
        <a href="/download?v={{ video_id }}&q=1080">
            <button>1080pでDL</button>
        </a>

        <a href="/download?v={{ video_id }}&q=720">
            <button>720pでDL</button>
        </a>

        <a href="/download?v={{ video_id }}&q=480">
            <button>480pでDL</button>
        </a>

        <a href="/download?v={{ video_id }}&q=360">
            <button>安定版360p</button>
        </a>
    </div>

    <br>

    <a href="/formats-check?v={{ video_id }}">
        <button>
            形式チェック
        </button>
    </a>

    <br>

    <a href="/runtime-check">
        <button>
            Runtime確認
        </button>
    </a>

    <br>

    <a href="/warmup?v={{ video_id }}">
        <button>
            事前準備
        </button>
    </a>

    <p class="note">
        1080p・720pは動画によって失敗する場合があります。その場合は720pか360pを試してください。
    </p>

</div>
{% endif %}

</body>
</html>
"""


@app.errorhandler(Exception)
def handle_exception(e):
    error_text = traceback.format_exc()
    return f"""
    <h2>アプリ内部エラー</h2>
    <pre>{html.escape(error_text)}</pre>
    """, 500


def get_video_id(text):
    if not text:
        return None

    text = text.strip()

    try:
        parsed = urlparse(text)

        if "youtube.com" in parsed.netloc:
            if parsed.path == "/watch":
                query = parse_qs(parsed.query)
                return query.get("v", [None])[0]

            if parsed.path.startswith("/shorts/"):
                return parsed.path.split("/shorts/")[1].split("/")[0]

        if "youtu.be" in parsed.netloc:
            return parsed.path.strip("/").split("/")[0]

    except Exception:
        return None

    return None


def get_url_from_request():
    video_id = request.args.get("v")

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}", video_id

    url = request.args.get("url")

    if url:
        return url, get_video_id(url)

    return None, None


def prepare_cookie():
    secret_cookie = "/etc/secrets/cookies.txt"
    cookie_path = "/tmp/cookies.txt"

    if not os.path.exists(secret_cookie):
        return None, "cookies.txt がRenderにありません"

    try:
        shutil.copy(secret_cookie, cookie_path)
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


def wait_for_mp4_file(folder, seconds=20):
    for _ in range(seconds):
        mp4_file = find_mp4_file(folder)

        if mp4_file and os.path.exists(mp4_file):
            return mp4_file

        time.sleep(1)

    return None


def get_quality_formats(quality):
    if quality == "1080":
        return [
            "137+140/136+140/135+140/134+140/18",
            "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/18",
            "18",
        ]

    if quality == "720":
        return [
            "136+140/135+140/134+140/18",
            "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/18",
            "18",
        ]

    if quality == "480":
        return [
            "135+140/134+140/18",
            "bv*[ext=mp4][height<=480]+ba[ext=m4a]/b[ext=mp4][height<=480]/18",
            "18",
        ]

    return [
        "18",
        "best[ext=mp4]/best",
    ]


@app.route("/", methods=["GET", "POST"])
def home():
    video_id = None
    error = None

    if request.method == "POST":
        text = request.form.get("input", "").strip()
        video_id = get_video_id(text)

        if not video_id:
            error = "YouTube URLを入力してください"

    return render_template_string(
        HTML,
        video_id=video_id,
        error=error
    )


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
    secret_cookie = "/etc/secrets/cookies.txt"

    if not os.path.exists(secret_cookie):
        return "NG: /etc/secrets/cookies.txt が存在しません"

    size = os.path.getsize(secret_cookie)

    with open(secret_cookie, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    has_youtube = "youtube.com" in text
    has_google = "google.com" in text
    has_sid = "SID" in text or "__Secure" in text
    starts_ok = "# Netscape HTTP Cookie File" in text[:200]

    return f"""
    <h2>Cookie Check</h2>
    <p>file: OK</p>
    <p>size: {size} bytes</p>
    <p>Netscape形式: {starts_ok}</p>
    <p>youtube.com cookieあり: {has_youtube}</p>
    <p>google.com cookieあり: {has_google}</p>
    <p>ログイン系cookieらしきものあり: {has_sid}</p>
    """


@app.route("/ffmpeg-check")
def ffmpeg_check():
    ffmpeg_path = get_ffmpeg_path()

    if not ffmpeg_path:
        return "ffmpeg NG"

    if os.path.exists(ffmpeg_path):
        return f"ffmpeg OK: {ffmpeg_path}"

    return "ffmpeg NG: ファイルが存在しません"


@app.route("/warmup")
def warmup():
    url, video_id = get_url_from_request()

    if not url:
        return "URLまたは動画IDがありません"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return cookie_error

    cmd = base_ytdlp_cmd(cookie_path)
    cmd = add_client_args(cmd, "web")

    cmd = cmd + [
        "-F",
        url
    ]

    try:
        code, stdout, stderr = run_command(cmd, timeout=180)

        output = stdout + "\n" + stderr

        return f"""
        <h2>事前準備 完了</h2>
        <p>return code: {code}</p>
        <p>このあと戻って、MP4ダウンロードを押してください。</p>
        <pre>{html.escape(output[:20000])}</pre>
        """

    except Exception as e:
        return f"事前準備エラー: {str(e)}"


@app.route("/formats-check")
def formats_check():
    url, video_id = get_url_from_request()

    if not url:
        return "URLまたは動画IDがありません"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return cookie_error

    clients = [
        {"name": "web", "cookie": True},
        {"name": "default", "cookie": True},
        {"name": "android_vr", "cookie": False},
        {"name": "ios", "cookie": True},
        {"name": "android", "cookie": True},
    ]

    outputs = []

    for item in clients:
        client = item["name"]
        use_cookie = item["cookie"]

        cmd = base_ytdlp_cmd(cookie_path if use_cookie else None)
        cmd = add_client_args(cmd, client)

        cmd = cmd + [
            "-F",
            url
        ]

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
COMMAND:
{' '.join(cmd)}

OUTPUT:
{output}
"""
            )

            if (
                " 137 " in output
                or " 136 " in output
                or " 135 " in output
                or " 134 " in output
                or " 140 " in output
                or " 18 " in output
            ):
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


@app.route("/download")
def download():
    url, video_id = get_url_from_request()

    if not url:
        return "URLまたは動画IDがありません"

    quality = request.args.get("q", "720")

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return cookie_error

    ffmpeg_path = get_ffmpeg_path()

    if not ffmpeg_path:
        return "ffmpegが取得できません"

    temp_dir = tempfile.mkdtemp(prefix="yt_")
    output_path = os.path.join(temp_dir, "%(id)s.%(ext)s")

    clients = [
        {"name": "web", "cookie": True},
        {"name": "default", "cookie": True},
        {"name": "android_vr", "cookie": False},
        {"name": "ios", "cookie": True},
        {"name": "android", "cookie": True},
    ]

    format_patterns = get_quality_formats(quality)

    errors = []

    for item in clients:
        client = item["name"]
        use_cookie = item["cookie"]

        for fmt in format_patterns:
            cmd = base_ytdlp_cmd(cookie_path if use_cookie else None)
            cmd = add_client_args(cmd, client)

            cmd = cmd + [
                "--ffmpeg-location",
                ffmpeg_path,

                "-f",
                fmt,

                "--merge-output-format",
                "mp4",

                "-o",
                output_path,

                url
            ]

            try:
                code, stdout, stderr = run_command(cmd, timeout=420)

                if code == 0:
                    mp4_file = wait_for_mp4_file(temp_dir, seconds=20)

                    if mp4_file and os.path.exists(mp4_file):
                        safe_video_id = video_id or get_video_id(url) or "video"

                        return send_file(
                            mp4_file,
                            as_attachment=True,
                            download_name=f"{safe_video_id}_{quality}p.mp4",
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
quality={quality}
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

    return f"""
    <h2>DL失敗</h2>
    <p>{quality}pで失敗しました。720pや360pも試してください。</p>
    <pre>{html.escape(error_output)}</pre>
    """


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
