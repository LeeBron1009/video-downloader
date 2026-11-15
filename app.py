import os, uuid, glob, shutil, requests
from flask import Flask, request, jsonify, send_file, render_template, Response
import yt_dlp

app = Flask(__name__)
TMP = "downloads"
os.makedirs(TMP, exist_ok=True)

# 在 Render 的環境變數 COOKIES_TXT 貼上 Netscape 格式 cookies（可選）
COOKIE_FILE = None
if os.environ.get("COOKIES_TXT"):
    COOKIE_FILE = "/tmp/cookies.txt"
    with open(COOKIE_FILE, "w") as f:
        f.write(os.environ["COOKIES_TXT"])

def common(opts):
    if COOKIE_FILE:
        opts["cookiefile"] = COOKIE_FILE
    return opts

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/info", methods=["POST"])
def info():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    kind = data.get("kind")
    if kind == "ig" and "instagram.com" not in url:
        return jsonify(error="請貼 Instagram 連結"), 400
    if kind == "yt" and "youtu" not in url:
        return jsonify(error="請貼 YouTube 連結"), 400
    opts = common({"quiet": True, "skip_download": True, "noplaylist": kind == "yt"})
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            d = y.extract_info(url, download=False)
    except Exception as e:
        return jsonify(error=str(e)[:400]), 500

    if kind == "yt":
        hs = sorted({f["height"] for f in d.get("formats", [])
                     if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
        return jsonify(title=d.get("title"), thumb=d.get("thumbnail"), heights=hs)

    entries = d.get("entries") or [d]
    items = [{"index": i,
              "thumb": e.get("thumbnail"),
              "video": e.get("vcodec") not in (None, "none")}
             for i, e in enumerate(entries, 1)]
    return jsonify(title=d.get("title"), items=items)

@app.route("/api/thumb")
def thumb():
    u = request.args.get("u", "")
    if not u.startswith("http"):
        return "", 400
    try:
        r = requests.get(u, timeout=15)
        return Response(r.content, content_type=r.headers.get("Content-Type", "image/jpeg"))
    except Exception:
        return "", 404

@app.route("/api/dl")
def dl():
    url = request.args.get("url", "")
    kind = request.args.get("kind")
    cont = request.args.get("cont", "mp4")
    job = os.path.join(TMP, uuid.uuid4().hex)
    os.makedirs(job)
    opts = common({
        "quiet": True,
        "outtmpl": os.path.join(job, "%(title).60s.%(ext)s"),
        "postprocessor_args": {"merger": ["-fflags", "+genpts", "-avoid_negative_ts", "make_zero"]},
    })
    if kind == "yt":
        h = int(request.args.get("h", 4320))
        opts["noplaylist"] = True
        opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/b"
        if cont == "mkv":
            opts["format_sort"] = ["res", "fps", "hdr:12", "vcodec", "br", "acodec"]
            opts["merge_output_format"] = "mkv"
        else:
            opts["format_sort"] = ["res", "vcodec:h264", "acodec:aac"]
            opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = "bv*+ba/b"
        opts["merge_output_format"] = "mp4"
        opts["playlist_items"] = request.args.get("idx", "1")
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        files = glob.glob(os.path.join(job, "*"))
        if not files:
            raise Exception("沒有下載到檔案")
        resp = send_file(files[0], as_attachment=True)
        resp.call_on_close(lambda: shutil.rmtree(job, ignore_errors=True))
        return resp
    except Exception as e:
        shutil.rmtree(job, ignore_errors=True)
        return jsonify(error=str(e)[:400]), 500

if __name__ == "__main__":
    app.run(debug=True)
