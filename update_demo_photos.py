#!/usr/bin/env python3
"""
CarsInStock — Demo Vehicle Photo Updater
Run on server: cd /home/eddie/carsinstock && source venv/bin/activate && python update_demo_photos.py
"""

import os
import sys
import requests
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Load Cloudinary creds from .env
load_dotenv("/home/eddie/carsinstock/.env")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "dbpa9qqtb"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

# ── Vehicle definitions ──────────────────────────────────────────────
VEHICLES = [
    {"public_id": "demo/2022_honda_accord",          "label": "2022 Honda Accord Sport — Pearl White"},
    {"public_id": "demo/2023_toyota_rav4",            "label": "2023 Toyota RAV4 XLE — Magnetic Gray"},
    {"public_id": "demo/2021_ford_f150",              "label": "2021 Ford F-150 XLT — Oxford White"},
    {"public_id": "demo/2022_chevy_equinox",          "label": "2022 Chevrolet Equinox LT — Mosaic Black"},
    {"public_id": "demo/2023_hyundai_tucson",         "label": "2023 Hyundai Tucson SEL — Shimmering Silver"},
    {"public_id": "demo/2020_bmw_330i",               "label": "2020 BMW 330i — Alpine White"},
    {"public_id": "demo/2022_jeep_grand_cherokee",    "label": "2022 Jeep Grand Cherokee Laredo — Diamond Black"},
    {"public_id": "demo/2021_nissan_altima",          "label": "2021 Nissan Altima SV — Gun Metallic"},
    {"public_id": "demo/2023_mazda_cx5",              "label": "2023 Mazda CX-5 Preferred — Soul Red"},
    {"public_id": "demo/2022_kia_telluride",          "label": "2022 Kia Telluride EX — Gravity Gray"},
]

# ── Paste image URLs here ────────────────────────────────────────────
# Put the direct image URL for each vehicle (in order, 1-10).
# Leave as empty string "" to skip that vehicle.
IMAGE_URLS = [
    "",  # 1. 2022 Honda Accord Sport Pearl White
    "",  # 2. 2023 Toyota RAV4 XLE Magnetic Gray
    "",  # 3. 2021 Ford F-150 XLT Oxford White
    "",  # 4. 2022 Chevrolet Equinox LT Mosaic Black
    "",  # 5. 2023 Hyundai Tucson SEL Shimmering Silver
    "",  # 6. 2020 BMW 330i Alpine White
    "",  # 7. 2022 Jeep Grand Cherokee Laredo Diamond Black
    "",  # 8. 2021 Nissan Altima SV Gun Metallic
    "",  # 9. 2023 Mazda CX-5 Soul Red
    "",  # 10. 2022 Kia Telluride EX Gravity Gray
]


def cleanup_bad_uploads():
    """Delete bad uploads from Home folder (root) and transparent/misnamed images."""
    print("\n🧹 CLEANUP — Scanning for bad uploads...")
    deleted = 0

    # Check root folder for stray car images
    try:
        result = cloudinary.api.resources(
            type="upload",
            prefix="",
            max_results=100,
        )
        for r in result.get("resources", []):
            pid = r["public_id"]
            # Skip anything already in a folder (like demo/)
            if "/" in pid:
                continue
            # Flag likely bad uploads (car-related names in root)
            lower = pid.lower()
            if any(term in lower for term in [
                "honda", "toyota", "ford", "chevy", "hyundai", "bmw",
                "jeep", "nissan", "mazda", "kia", "accord", "rav4",
                "f150", "f-150", "equinox", "tucson", "330i",
                "cherokee", "altima", "cx5", "cx-5", "telluride",
                "demo", "vehicle", "car_", "stock_photo",
            ]):
                print(f"  🗑  Deleting root image: {pid}")
                cloudinary.uploader.destroy(pid, invalidate=True)
                deleted += 1
    except Exception as e:
        print(f"  ⚠️  Error scanning root folder: {e}")

    # Check demo folder for misnamed/bad images
    try:
        result = cloudinary.api.resources(
            type="upload",
            prefix="demo/",
            max_results=100,
        )
        # Known good public IDs
        good_ids = {v["public_id"] for v in VEHICLES}
        for r in result.get("resources", []):
            pid = r["public_id"]
            if pid not in good_ids:
                print(f"  🗑  Deleting bad demo image: {pid}")
                cloudinary.uploader.destroy(pid, invalidate=True)
                deleted += 1
    except Exception as e:
        print(f"  ⚠️  Error scanning demo folder: {e}")

    print(f"  ✅ Cleanup done — {deleted} image(s) deleted.\n")


def upload_vehicle(vehicle, url):
    """Download from URL and upload to Cloudinary."""
    label = vehicle["label"]
    public_id = vehicle["public_id"]

    print(f"📸 {label}")
    print(f"   Downloading: {url[:80]}...")

    try:
        result = cloudinary.uploader.upload(
            url,
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            resource_type="image",
            folder="",  # public_id already includes demo/
        )
        final_url = result.get("secure_url", "")
        print(f"   ✅ Uploaded → {final_url}")
        return True
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False


def verify_uploads():
    """List all images in demo/ folder to confirm."""
    print("\n🔍 VERIFICATION — Images in demo/ folder:")
    try:
        result = cloudinary.api.resources(
            type="upload",
            prefix="demo/",
            max_results=30,
        )
        for r in sorted(result.get("resources", []), key=lambda x: x["public_id"]):
            pid = r["public_id"]
            fmt = r.get("format", "?")
            w = r.get("width", "?")
            h = r.get("height", "?")
            print(f"   ✅ {pid}.{fmt} ({w}x{h})")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")


def main():
    print("=" * 60)
    print("  CarsInStock — Demo Vehicle Photo Updater")
    print("=" * 60)

    # Verify Cloudinary connection
    try:
        cloudinary.api.ping()
        print("☁️  Cloudinary connected.\n")
    except Exception as e:
        print(f"❌ Cloudinary connection failed: {e}")
        sys.exit(1)

    # Step 1: Cleanup
    cleanup_bad_uploads()

    # Step 2: Upload vehicles that have URLs
    urls_provided = [u for u in IMAGE_URLS if u.strip()]
    if not urls_provided:
        print("⚠️  No image URLs provided yet!")
        print("   Edit this script and paste URLs into the IMAGE_URLS list.")
        print("   Then run again.\n")
        verify_uploads()
        return

    print(f"📤 UPLOADING — {len(urls_provided)} image(s)...\n")
    success = 0
    failed = 0

    for i, (vehicle, url) in enumerate(zip(VEHICLES, IMAGE_URLS)):
        if not url.strip():
            print(f"⏭  Skipping #{i+1}: {vehicle['label']} (no URL)")
            continue
        if upload_vehicle(vehicle, url):
            success += 1
        else:
            failed += 1
        print()

    print(f"📊 Results: {success} uploaded, {failed} failed, {10 - success - failed} skipped")

    # Step 3: Verify
    verify_uploads()

    print("\n🌐 Check the demo page: https://carsinstock.com/demo")
    print("   (Cloudinary CDN cache may take 1-2 min to update)\n")


if __name__ == "__main__":
    main()

