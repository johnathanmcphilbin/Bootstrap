import os
import uuid
import time
import smtplib
from email.mime.text import MIMEText
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/api/*": {"origins": os.environ.get("ALLOWED_ORIGIN", "*")}})

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
NOTIFY_EMAIL = "johnathanmcphilbin2@gmail.com"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY environment variables must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_notification(subject, body):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = GMAIL_USER
        msg["To"] = NOTIFY_EMAIL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
    except Exception:
        pass  # never let email errors break the main request

def get_tier(score):
    if score is None:
        return "pending"
    if score >= 85:
        return "Funded"
    elif score >= 70:
        return "Series A"
    elif score >= 50:
        return "Pre-seed"
    else:
        return "Bootstrapped"

# Simple in-memory rate limiter: max requests per window per IP
_rate_store = defaultdict(list)

def rate_limit(max_requests=5, window=60):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
            key = f"{f.__name__}:{ip}"
            now = time.time()
            _rate_store[key] = [t for t in _rate_store[key] if now - t < window]
            if len(_rate_store[key]) >= max_requests:
                return jsonify({"error": "Too many requests. Slow down."}), 429
            _rate_store[key].append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        password = request.headers.get("X-Admin-Password")
        if password != ADMIN_PASSWORD:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/admin")
def admin():
    return send_from_directory("static", "admin.html")

@app.route("/resources")
def resources():
    return send_from_directory("static", "resources.html")

ALLOWED_BUCKETS = {"videos", "decks"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
ALLOWED_DECK_TYPES = {"application/pdf"}
MAX_SIZES = {"videos": 200 * 1024 * 1024, "decks": 20 * 1024 * 1024}
ALLOWED_EXTENSIONS = {"videos": {"mp4", "mov", "webm"}, "decks": {"pdf"}}
ALLOWED_STATUSES = {"pending", "approved", "rejected"}

@app.route("/api/upload-url", methods=["POST"])
@rate_limit(max_requests=20, window=60)
def get_upload_url():
    try:
        data = request.get_json()
        bucket = data.get("bucket")
        content_type = data.get("content_type")
        file_size = data.get("file_size", 0)
        filename = data.get("filename", "file")

        if bucket not in ALLOWED_BUCKETS:
            return jsonify({"error": "Invalid bucket"}), 400

        allowed_types = ALLOWED_VIDEO_TYPES if bucket == "videos" else ALLOWED_DECK_TYPES
        if content_type not in allowed_types:
            return jsonify({"error": f"File type not allowed: {content_type}"}), 400

        if file_size > MAX_SIZES[bucket]:
            mb = MAX_SIZES[bucket] // (1024 * 1024)
            return jsonify({"error": f"File too large (max {mb}MB)"}), 400

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS[bucket]:
            return jsonify({"error": f"File extension not allowed: .{ext}"}), 400
        path = f"{uuid.uuid4().hex}.{ext}"

        result = supabase.storage.from_(bucket).create_signed_upload_url(path)
        signed_url = result.get("signedURL") or result.get("signed_url")
        if not signed_url:
            return jsonify({"error": "Could not generate upload URL"}), 500

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"
        return jsonify({"signed_url": signed_url, "public_url": public_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/interest", methods=["POST"])
@rate_limit(max_requests=3, window=300)
def interest():
    try:
        data = request.get_json()
        if not data.get("name") or not data.get("age") or not data.get("country"):
            return jsonify({"error": "Missing required fields"}), 400
        age = int(data["age"])
        if age < 10 or age > 19:
            return jsonify({"error": "Must be 19 or under to participate"}), 400
        supabase.table("interest").insert({
            "name": data["name"],
            "age": age,
            "country": data["country"],
            "email": data.get("email"),
        }).execute()
        send_notification(
            f"New interest signup: {data['name']}",
            f"Name: {data['name']}\n"
            f"Age: {data['age']}\n"
            f"Country: {data['country']}\n"
            f"Email: {data.get('email') or 'not provided'}\n"
        )
        return jsonify({"success": True}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
    try:
        result = supabase.table("submissions") \
            .select("id, project_name, builder_name, live_url, github_url, score, tier, created_at") \
            .eq("status", "approved") \
            .not_.is_("score", "null") \
            .order("score", desc=True) \
            .execute()
        entries = []
        for i, row in enumerate(result.data):
            entries.append({
                "rank": i + 1,
                "id": row["id"],
                "project_name": row["project_name"],
                "builder_name": row["builder_name"],
                "live_url": row["live_url"],
                "github_url": row["github_url"],
                "score": row["score"],
                "tier": get_tier(row["score"]),
                "created_at": row["created_at"],
            })
        return jsonify({"leaderboard": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/submit", methods=["POST"])
@rate_limit(max_requests=5, window=300)
def submit():
    try:
        data = request.get_json()
        required = ["project_name", "builder_name", "live_url", "github_url", "pitch_url"]
        for field in required:
            if not data.get(field):
                return jsonify({"error": f"Missing field: {field}"}), 400
        result = supabase.table("submissions").insert({
            "project_name": data["project_name"],
            "builder_name": data["builder_name"],
            "live_url": data["live_url"],
            "github_url": data["github_url"],
            "pitch_url": data["pitch_url"],
            "deck_url": data.get("deck_url"),
            "score": None,
            "tier": "pending",
            "status": "pending",
        }).execute()
        sub = result.data[0]
        send_notification(
            f"New submission: {data['project_name']}",
            f"Project: {data['project_name']}\n"
            f"Builder: {data['builder_name']}\n"
            f"Live URL: {data['live_url']}\n"
            f"GitHub: {data['github_url']}\n"
            f"Pitch: {data['pitch_url']}\n"
            f"Deck: {data.get('deck_url') or 'none'}\n"
            f"ID: {sub['id']}\n\n"
            f"Review at: https://bootstrap-production-e275.up.railway.app/admin"
        )
        return jsonify({"success": True, "id": sub["id"]}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/interest/count", methods=["GET"])
def interest_count():
    try:
        result = supabase.table("interest").select("id", count="exact").execute()
        return jsonify({"count": result.count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/interest", methods=["GET"])
@require_admin
def admin_interest():
    try:
        result = supabase.table("interest") \
            .select("*") \
            .order("created_at", desc=True) \
            .execute()
        return jsonify({"interest": result.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/submissions", methods=["GET"])
@require_admin
def admin_submissions():
    try:
        result = supabase.table("submissions") \
            .select("*") \
            .order("created_at", desc=True) \
            .execute()
        return jsonify({"submissions": result.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/submissions/<sub_id>", methods=["PATCH"])
@require_admin
def update_submission(sub_id):
    try:
        data = request.get_json()
        update = {}
        if "score" in data:
            score = int(data["score"])
            update["score"] = score
            update["tier"] = get_tier(score)
        if "status" in data:
            if data["status"] not in ALLOWED_STATUSES:
                return jsonify({"error": "Invalid status"}), 400
            update["status"] = data["status"]
        result = supabase.table("submissions") \
            .update(update) \
            .eq("id", sub_id) \
            .execute()
        return jsonify({"success": True, "data": result.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
