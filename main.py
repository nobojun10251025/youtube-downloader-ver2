from flask import Flask, request, render_template_string, send_file
import os
import shutil
import tempfile
import subprocess
import sys
import traceback
import html
import json
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
            max-height: 500px;
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

        .quality-buttons button {
            width: 170px;
            margin: 6px;
        }

        .info-grid {
            text-align: left;
            max-width: 650px;
            margin: 0 auto;
            line-height: 1.7;
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
            <p><strong>取得できる画質：</strong>{{ analysis.qualities_text }}</p>
            <p class="ok"><strong>おすすめ：</strong>{{ analysis.recommended }}p</p>

            {% if analysis.warning %}
            <p class="warning">{{ analysis.warning }}</p>
            {% endif %}

            <p class="note">{{ analysis.message }}</p>
        </div>
        {% else %}
        <p class="danger">動画情報の解析に失敗しました</p>
        <p>{{ analysis.reason }}</p>
        {% endif %}
    </div>
    {% endif %}

    <br>

    <div class="quality-buttons">
        <a href="/download?v={{ video_id }}&q=auto">
            <button>
                自動・高画質DL
            </button>
        </a>

        <a href="/download?v={{ video_id }}&q=1080">
            <button>
                1080p優先
            </button>
        </a>

        <a href="/download?v={{ video_id }}&q=720">
            <button>
                720p優先
            </button>
        </a>

        <a href="/download?v={{ video_id }}&q=360">
            <button>
                安定版360p
            </button>
        </a>
    </div>

    <br>

    <a href="/formats-check?v={{ video_id }}">
        <button>
            形式チェック
        </button>
    </a>

    <a href="/runtime-check">
        <button>
            Runtime確認
        </button>
    </a>

    <p class="note">
        この版はnot found対策として、ダウンロード完了後すぐ同じリクエスト内でMP4を返します。
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
        return "YouTube側にbot判定されています。cookies.txtが切れている、またはログイン状態が弱い可能性があります。cookies.txtを作り直してください。"

    if "requested format is not available" in lower:
        return "指定した画質がこの動画では取得できません。720pや360pなど、低い画質を試してください。"

    if "only images are available" in lower or ("storyboard" in lower and "mp4" not in lower):
        return "動画本体ではなく、シークバー用のプレビュー画像だけが見えています。Deno、cookies、またはRenderのIP制限が原因の可能性があります。"

    if "no supported javascript runtime" in lower or ("deno" in lower and "no such file" in lower):
        return "Denoが正しく動いていません。Build CommandでDenoが入っているか、runtime-checkを確認してください。"

    if "ffmpeg" in lower:
        return "ffmpeg関連のエラーです。映像と音声の結合に失敗している可能性があります。ffmpeg-checkを確認してください。"

    if "timeout" in lower or "timed out" in lower or "タイムアウト" in text:
        return "処理が時間切れになりました。動画が長い、画質が高すぎる、またはRenderの処理時間制限に近い可能性があります。360pで試してください。"

    if "http error 403" in lower or "forbidden" in lower:
        return "YouTube側にアクセスを拒否されています。cookies.txtの更新、または時間を置いて再試行してください。"

    if "read-only file system" in lower:
        return "RenderのSecret Fileを直接書き換えようとして失敗しています。cookies.txtを/tmpにコピーして使う必要があります。"

    if "file is missing" in lower or "file not found" in lower or "not found" in lower:
        return "ファイル生成直後の取得に失敗しています。この版では直接返す方式にしているので、再試行するか360pで試してください。"

    return "原因を特定できませんでした。形式チェックで取得可能な画質を確認し、低い画質から試してください。"


def analyze_formats(formats):
    heights = set()
    has_audio = False
    has_18 = False

    for f in formats:
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        ext = f.get("ext")
        height = f.get("height")
        format_id = str(f.get("format_id", ""))

        if format_id == "18":
            has_18 = True
            heights.add(360)
            has_audio = True

        if acodec and acodec != "none" and ext in ["m4a", "mp4", "webm"]:
            has_audio = True

        if vcodec and vcodec != "none" and height:
            try:
                heights.add(int(height))
            except Exception:
                pass

    qualities = []

    if has_audio:
        if any(h >= 1080 for h in heights):
            qualities.append(1080)

        if any(h >= 720 for h in heights):
            qualities.append(720)

        if any(h >= 480 for h in heights):
            qualities.append(480)

        if any(h >= 360 for h in heights) or has_18:
            qualities.append(360)

    qualities = sorted(list(set(qualities)), reverse=True)

    return qualities


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


def analyze_video(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return {
            "ok": False,
            "reason": cookie_error
        }

    clients = [
        {"name": "web", "cookie": True},
        {"name": "default", "cookie": True},
        {"name": "android_vr", "cookie": False},
        {"name": "ios", "cookie": True},
        {"name": "android", "cookie": True},
    ]

    last_output = ""

    for item in clients:
        client = item["name"]
        use_cookie = item["cookie"]

        cmd = base_ytdlp_cmd(cookie_path if use_cookie else None)
        cmd = add_client_args(cmd, client)

        cmd = cmd + [
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

            qualities = analyze_formats(formats)

            if not qualities:
                continue

            warning = ""
            message = "取得できる画質を自動判定しました。"

            if duration and duration >= 1800:
                warning = "この動画は30分以上あります。Renderでは高画質DLが失敗しやすいので、360p推奨です。"
            elif duration and duration >= 600:
                warning = "この動画は10分以上あります。1080pは失敗する可能性があります。720pか360pがおすすめです。"

            if qualities == [360]:
                message = "この動画はRender上では360pのみ確認できました。高画質ボタンを押しても360pになる可能性が高いです。"

            if 720 in qualities:
                recommended = 720
            else:
                recommended = qualities[-1]

            if duration and duration >= 600:
                if 360 in qualities:
                    recommended = 360
                elif 480 in qualities:
                    recommended = 480

            return {
                "ok": True,
                "title": html.escape(title),
                "duration": duration,
                "duration_text": seconds_to_text(duration),
                "qualities": qualities,
                "qualities_text": " / ".join([f"{q}p" for q in qualities]),
                "recommended": recommended,
                "warning": warning,
                "message": message,
                "client": client
            }

        except Exception as e:
            last_output += "\n" + str(e)
            continue

    return {
        "ok": False,
        "reason": explain_error(last_output)
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

    if quality == "360":
        return [
            "18",
            "best[ext=mp4]/best",
        ]

    # auto
    return [
        "137+140/136+140/135+140/134+140/18",
        "136+140/135+140/134+140/18",
        "135+140/134+140/18",
        "134+140/18",
        "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/18",
        "18",
    ]


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


@app.route("/download")
def download():
    video_id = request.args.get("v")
    quality = request.args.get("q", "auto")

    if not video_id:
        return "動画IDがありません", 400

    url = f"https://www.youtube.com/watch?v={video_id}"

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        return f"""
        <h2>DL失敗</h2>
        <p>{html.escape(cookie_error)}</p>
        <p>{html.escape(explain_error(cookie_error))}</p>
        """, 500

    ffmpeg_path = get_ffmpeg_path()

    if not ffmpeg_path:
        return """
        <h2>DL失敗</h2>
        <p>ffmpegが取得できません</p>
        <p>ffmpeg-checkを確認してください。</p>
        """, 500

    temp_dir = tempfile.mkdtemp(prefix="yt_")
    output_path = os.path.join(temp_dir, "%(title).80s [%(id)s].%(ext)s")

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

                output = stdout + "\n" + stderr

                if code == 0:
                    mp4_file = find_mp4_file(temp_dir)

                    if mp4_file and os.path.exists(mp4_file):
                        filename = os.path.basename(mp4_file)

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

    reason = explain_error(error_output)

    return f"""
    <h2>DL失敗</h2>
    <p><strong>日本語の原因候補：</strong>{html.escape(reason)}</p>
    <p>{html.escape(quality)} で失敗しました。720pや360pも試してください。</p>
    <pre>{html.escape(error_output)}</pre>
    """, 500


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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
