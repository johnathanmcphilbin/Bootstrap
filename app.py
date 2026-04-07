import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY environment variables must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

ALLOWED_BUCKETS = {"videos", "decks"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
ALLOWED_DECK_TYPES = {"application/pdf"}
MAX_SIZES = {"videos": 200 * 1024 * 1024, "decks": 20 * 1024 * 1024}

@app.route("/api/upload-url", methods=["POST"])
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
        path = f"{uuid.uuid4().hex}.{ext}"

        result = supabase.storage.from_(bucket).create_signed_upload_url(path)
        signed_url = result.get("signedURL") or result.get("signed_url")
        if not signed_url:
            return jsonify({"error": "Could not generate upload URL"}), 500

        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"
        return jsonify({"signed_url": signed_url, "public_url": public_url})
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
        return jsonify({"success": True, "id": result.data[0]["id"]}), 201
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
