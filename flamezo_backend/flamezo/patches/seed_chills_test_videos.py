"""
Patch: update dev seed Chills records with real publicly-accessible video URLs.
Run with: bench --site dev.flamezo.in execute flamezo_backend.flamezo.patches.seed_chills_test_videos
"""

import frappe

# Free public short-form videos (Google public sample bucket)
TEST_VIDEOS = [
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
     "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=600"),
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
     "https://images.unsplash.com/photo-1568702846914-96b305d2aaeb?w=600"),
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
     "https://images.unsplash.com/photo-1520568961470-7b8f7fcd1b41?w=600"),
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4",
     "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=600"),
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4",
     "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=600"),
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/SubaruOutbackOnStreetAndDirt.mp4",
     "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=600"),
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/VolkswagenGTIReview.mp4",
     "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=600"),
    ("https://storage.googleapis.com/gtv-videos-bucket/sample/WeAreGoingOnBullrun.mp4",
     "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600"),
]


def execute():
    rows = frappe.db.sql(
        "SELECT name FROM `tabChills` WHERE status='published' ORDER BY published_at DESC LIMIT 50",
        as_dict=True,
    )
    if not rows:
        print("No published Chills found — nothing to patch.")
        return

    for i, row in enumerate(rows):
        video_url, thumbnail_url = TEST_VIDEOS[i % len(TEST_VIDEOS)]
        frappe.db.sql(
            "UPDATE `tabChills` SET video_url=%s, thumbnail_url=%s WHERE name=%s",
            [video_url, thumbnail_url, row.name],
        )
        print(f"  Patched {row.name} → {video_url.split('/')[-1]}")

    frappe.db.commit()
    print(f"\nDone. {len(rows)} Chills records updated with working video URLs.")
