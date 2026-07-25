"""
Upload local Boojee Cafe videos to R2 and print bench console script to seed Chills.

Usage:
  export R2_ENDPOINT="https://<accountid>.r2.cloudflarestorage.com"
  export R2_ACCESS_KEY="..."
  export R2_SECRET_KEY="..."
  export R2_BUCKET="..."
  export R2_PUBLIC_URL="https://cdn.flamezo.in"  # or whatever your public URL is
  python3 upload_chills_videos.py
"""

import os
import sys
import uuid
import mimetypes

try:
    import boto3
    from botocore.config import Config
except ImportError:
    print("boto3 not installed. Run: pip install boto3")
    sys.exit(1)

# ── Config from env ───────────────────────────────────────────────────────────

ENDPOINT   = os.environ.get("R2_ENDPOINT", "").strip()
ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "").strip()
SECRET_KEY = os.environ.get("R2_SECRET_KEY", "").strip()
BUCKET     = os.environ.get("R2_BUCKET", "").strip()
PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "").strip().rstrip("/")

if not all([ENDPOINT, ACCESS_KEY, SECRET_KEY, BUCKET, PUBLIC_URL]):
    print("Missing env vars. Set: R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET, R2_PUBLIC_URL")
    sys.exit(1)

# ── Find videos ───────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../" * 6))  # up to Flamezo-Project
BOOJEE_DIR = os.path.join(PROJECT_ROOT, "flamezo-web/public/boojee-cafe")

video_files = []
for root, _, files in os.walk(BOOJEE_DIR):
    for f in sorted(files):
        if f.lower().endswith((".mp4", ".mov")):
            video_files.append(os.path.join(root, f))

if not video_files:
    print(f"No videos found in {BOOJEE_DIR}")
    sys.exit(1)

print(f"Found {len(video_files)} videos in {BOOJEE_DIR}\n")

# ── Upload ────────────────────────────────────────────────────────────────────

client = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="auto",
)

uploaded_urls = []

for path in video_files:
    filename = os.path.basename(path)
    object_key = f"chills/seed/{uuid.uuid4().hex[:8]}_{filename}"
    content_type = mimetypes.guess_type(path)[0] or "video/mp4"
    size_mb = os.path.getsize(path) / (1024 * 1024)

    print(f"Uploading {filename} ({size_mb:.1f} MB) ...", end=" ", flush=True)
    try:
        with open(path, "rb") as f:
            client.put_object(
                Bucket=BUCKET,
                Key=object_key,
                Body=f,
                ContentType=content_type,
            )
        cdn_url = f"{PUBLIC_URL}/{object_key}"
        uploaded_urls.append(cdn_url)
        print(f"✓  {cdn_url}")
    except Exception as e:
        print(f"✗  {e}")

print(f"\n{len(uploaded_urls)} / {len(video_files)} uploaded.\n")

# ── Print bench console seed script ──────────────────────────────────────────

if uploaded_urls:
    print("=" * 72)
    print("Paste this into: bench --site dev.flamezo.in console")
    print("=" * 72)
    print()
    urls_repr = repr(uploaded_urls)
    print(f"""videos = {urls_repr}
rows = frappe.db.sql("SELECT name FROM `tabChills` WHERE status='published' ORDER BY published_at DESC LIMIT {len(uploaded_urls)}", as_dict=True)
for i, r in enumerate(rows[:len(videos)]):
    frappe.db.sql("UPDATE `tabChills` SET video_url=%s WHERE name=%s", [videos[i % len(videos)], r.name])
    print(r.name, "→", videos[i % len(videos)].split("/")[-1])
frappe.db.commit()
print("Done:", len(rows), "records")""")
