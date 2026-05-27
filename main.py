from flask import Flask, request, render_template_string, send_file, jsonify
import os
import shutil
import tempfile
import subprocess
import sys
import traceback
import html
import time
import uuid
import threading
import re
import imageio_ffmpeg
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

JOBS = {}

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

        button:disabled {
            background: #555;
            cursor: not-allowed;
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
            max-height: 350px;
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

        .quality-buttons button {
            width: 170px;
            margin: 6px;
        }

        .progress-wrap {
            width: 90%;
            max-width: 600px;
            margin: 15px auto;
            background: #333;
            border-radius: 20px;
            overflow: hidden;
        }

        .progress-bar {
            width: 0%;
            background: red;
            height: 24px;
            line-height: 24px;
            color: white;
            transition: width 0.3s;
        }

        #downloadLink {
            display: none;
            margin-top: 15px;
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
        <button onclick="startDownload('{{ video_id }}', 'auto')">
            自動・高画質DL
        </button>

        <button onclick="startDownload('{{ video_id }}', '1080')">
            1080p優先
        </button>

        <button onclick="startDownload('{{ video_id }}', '720')">
            720p優先
        </button>

        <button onclick="startDownload('{{ video_id }}', '360')">
            安定版360p
        </button>
    </div>

    <div class="progress-wrap">
        <div id="progressBar" class="progress-bar">0%</div>
    </div>

    <p id="statusText" class="note">
        待機中
    </p>

    <a id="downloadLink" href="#">
        <button>
            完成したMP4を保存
        </button>
    </a>

    <pre id="logBox"></pre>

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
        自動・高画質DLは、1080p → 720p → 480p → 360pの順で試します。
    </p>

</div>
{% endif %}

<script>
let polling = null;

function setButtonsDisabled(disabled) {
    document.querySelectorAll(".quality-buttons button").forEach(btn => {
        btn.disabled = disabled;
    });
}

function startDownload(videoId, quality) {
    setButtonsDisabled(true);

    document.getElementById("downloadLink").style.display = "none";
    document.getElementById("logBox").textContent = "";
    document.getElementById("statusText").textContent = "準備中...";
    updateProgress(0);

    fetch("/start-download", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            v: videoId,
            q: quality
        })
    })
    .then(res => res.json())
    .then(data => {
        if (!data.job_id) {
            document.getElementById("statusText").textContent = "開始失敗";
            document.getElementById("logBox").textContent = data.error || "不明なエラー";
            setButtonsDisabled(false);
            return;
        }

        pollProgress(data.job_id);
    })
    .catch(err => {
        document.getElementById("statusText").textContent = "通信エラー";
        document.getElementById("logBox").textContent = err;
        setButtonsDisabled(false);
    });
}

function updateProgress(percent) {
    const bar = document.getElementById("progressBar");
    percent = Math.max(0, Math.min(100, percent));
    bar.style.width = percent + "%";
    bar.textContent = percent + "%";
}

function pollProgress(jobId) {
    if (polling) {
        clearInterval(polling);
    }

    polling = setInterval(() => {
        fetch("/progress/" + jobId)
        .then(res => res.json())
        .then(data => {
            updateProgress(data.progress || 0);
            document.getElementById("statusText").textContent = data.status || "";
            document.getElementById("logBox").textContent = data.log || "";

            if (data.state === "done") {
                clearInterval(polling);
                updateProgress(100);
                document.getElementById("statusText").textContent = "完了しました";
                const link = document.getElementById("downloadLink");
                link.href = "/file/" + jobId;
                link.style.display = "inline-block";
                setButtonsDisabled(false);
            }

            if (data.state === "error") {
                clearInterval(polling);
                document.getElementById("statusText").textContent = "失敗しました";
                setButtonsDisabled(false);
            }
        })
        .catch(err => {
            clearInterval(polling);
            document.getElementById("statusText").textContent = "進捗取得エラー";
            document.getElementById("logBox").textContent = err;
            setButtonsDisabled(false);
        });
    }, 1500);
}
</script>

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


def update_job(job_id, **kwargs):
    if job_id in JOBS:
        JOBS[job_id].update(kwargs)


def append_log(job_id, text):
    if job_id not in JOBS:
        return

    old = JOBS[job_id].get("log", "")
    new = old + text + "\n"

    if len(new) > 20000:
        new = new[-20000:]

    JOBS[job_id]["log"] = new


def parse_progress(line):
    match = re.search(r"(\\d+(?:\\.\\d+)?)%", line)

    if match:
        try:
            return int(float(match.group(1)))
        except Exception:
            return None

    return None


def run_ytdlp_with_progress(job_id, cmd, timeout=420):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    start_time = time.time()

    while True:
        if process.poll() is not None:
            break

        if time.time() - start_time > timeout:
            process.kill()
            return 124

        line = process.stdout.readline()

        if not line:
            time.sleep(0.2)
            continue

        line = line.strip()

        if line:
            append_log(job_id, line)

            if "[download]" in line:
                update_job(job_id, status="ダウンロード中...")

                progress = parse_progress(line)

                if progress is not None:
                    update_job(job_id, progress=min(progress, 90))

            if "Merging formats" in line or "[Merger]" in line:
                update_job(job_id, status="映像と音声を結合中...", progress=92)

            if "Extracting URL" in line:
                update_job(job_id, status="動画情報を取得中...", progress=5)

            if "Downloading webpage" in line:
                update_job(job_id, status="YouTubeに接続中...", progress=10)

            if "Solving JS challenges" in line:
                update_job(job_id, status="JS認証を処理中...", progress=15)

    remaining = process.stdout.read()

    if remaining:
        for line in remaining.splitlines():
            append_log(job_id, line)

    return process.returncode


def download_worker(job_id, video_id, quality):
    url = f"https://www.youtube.com/watch?v={video_id}"

    update_job(
        job_id,
        state="running",
        status="準備中...",
        progress=1
    )

    cookie_path, cookie_error = prepare_cookie()

    if cookie_error:
        update_job(
            job_id,
            state="error",
            status="cookieエラー",
            progress=0
        )
        append_log(job_id, cookie_error)
        return

    ffmpeg_path = get_ffmpeg_path()

    if not ffmpeg_path:
        update_job(
            job_id,
            state="error",
            status="ffmpegエラー",
            progress=0
        )
        append_log(job_id, "ffmpegが取得できません")
        return

    temp_dir = tempfile.mkdtemp(prefix=f"yt_{job_id}_")
    output_path = os.path.join(temp_dir, "%(title).80B [%(id)s].%(ext)s")

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
            update_job(
                job_id,
                status=f"{client} / {fmt} を試行中...",
                progress=max(JOBS[job_id].get("progress", 1), 5)
            )

            cmd = base_ytdlp_cmd(cookie_path if use_cookie else None)
            cmd = add_client_args(cmd, client)

            cmd = cmd + [
                "--ffmpeg-location",
                ffmpeg_path,

                "--newline",

                "-f",
                fmt,

                "--merge-output-format",
                "mp4",

                "-o",
                output_path,

                url
            ]

            append_log(job_id, "----------------------------------------")
            append_log(job_id, f"client={client}, cookie={use_cookie}, format={fmt}")

            try:
                code = run_ytdlp_with_progress(job_id, cmd, timeout=420)

                if code == 0:
                    update_job(job_id, status="ファイル確認中...", progress=95)

                    mp4_file = find_mp4_file(temp_dir)

                    if mp4_file and os.path.exists(mp4_file):
                        filename = os.path.basename(mp4_file)

                        update_job(
                            job_id,
                            state="done",
                            status="完了",
                            progress=100,
                            file_path=mp4_file,
                            filename=filename
                        )
                        append_log(job_id, f"完成: {filename}")
                        return

                    any_file = find_any_file(temp_dir)

                    if any_file:
                        errors.append(
                            f"mp4なし。生成ファイル: {os.path.basename(any_file)}"
                        )
                    else:
                        errors.append(
                            "成功扱いだがファイルなし"
                        )

                else:
                    errors.append(
                        f"client={client}, format={fmt}, code={code}"
                    )

            except Exception as e:
                errors.append(
                    f"client={client}, format={fmt}, 例外: {str(e)}"
                )

            append_log(job_id, "この条件では失敗。次を試します。")

    update_job(
        job_id,
        state="error",
        status="すべて失敗しました",
        progress=0
    )

    append_log(job_id, "失敗一覧:")
    for err in errors:
        append_log(job_id, err)


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


@app.route("/start-download", methods=["POST"])
def start_download():
    data = request.get_json(silent=True) or {}

    video_id = data.get("v")
    quality = data.get("q", "auto")

    if not video_id:
        return jsonify({
            "error": "動画IDがありません"
        }), 400

    job_id = uuid.uuid4().hex

    JOBS[job_id] = {
        "state": "queued",
        "status": "待機中",
        "progress": 0,
        "log": "",
        "file_path": None,
        "filename": None,
        "created_at": time.time(),
    }

    thread = threading.Thread(
        target=download_worker,
        args=(job_id, video_id, quality),
        daemon=True
    )

    thread.start()

    return jsonify({
        "job_id": job_id
    })


@app.route("/progress/<job_id>")
def progress(job_id):
    job = JOBS.get(job_id)

    if not job:
        return jsonify({
            "state": "error",
            "status": "ジョブが見つかりません",
            "progress": 0,
            "log": ""
        }), 404

    return jsonify(job)


@app.route("/file/<job_id>")
def file_download(job_id):
    job = JOBS.get(job_id)

    if not job:
        return "ジョブが見つかりません", 404

    if job.get("state") != "done":
        return "まだ完了していません", 400

    file_path = job.get("file_path")

    if not file_path or not os.path.exists(file_path):
        return "ファイルが見つかりません", 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=job.get("filename") or "video.mp4",
        conditional=False,
        max_age=0
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
