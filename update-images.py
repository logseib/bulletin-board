#!/usr/bin/env python3
"""
Scans the images/ directory for all .jpg / .jpeg files and writes images/manifest.js
so index.html automatically displays every JPEG in images/ without manual edits,
including each image's natural width and height so portrait/vertical and landscape/horizontal
photos render in their true aspect ratio.
Can be run once (--once) or as a continuous lightweight folder watcher (--watch).
"""
import datetime
import json
import os
import re
import struct
import sys
import time
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
META_FILE = os.path.join(IMAGES_DIR, ".photo-meta.json")
MANIFEST_JS = os.path.join(IMAGES_DIR, "manifest.js")

INITIAL_FILM_SCANS = {
    "1.jpg": ("Film Scan 1 · 10/20/2026", "2026-10-20T09:46:01", "2026-10-20T09:46:01"),
    "2.jpg": ("Film Scan 2 · 10/20/2026", "2026-10-20T09:46:02", "2026-10-20T09:46:02"),
    "3.jpg": ("Film Scan 3 · 10/20/2026", "2026-10-20T09:46:03", "2026-10-20T09:46:03"),
    "4.jpg": ("Film Scan 4 · 10/20/2026", "2026-10-20T09:46:04", "2026-10-20T09:46:04"),
    "5.jpg": ("Film Scan 5 · 10/20/2026", "2026-10-20T09:46:05", "2026-10-20T09:46:05"),
    "6.jpg": ("Film Scan 6 · 10/20/2026", "2026-10-20T09:46:06", "2026-10-20T09:46:06"),
    "7.jpg": ("Film Scan 7 · 10/20/2026", "2026-10-20T09:46:07", "2026-10-20T09:46:07"),
    "8.jpg": ("Film Scan 8 · 10/20/2026", "2026-10-20T09:46:08", "2026-10-20T09:46:08"),
    "10.jpg": ("Film Scan 10 · 10/20/2026", "2026-10-20T09:46:10", "2026-10-20T09:46:10"),
    "11.jpg": ("Film Scan 11 · 10/20/2026", "2026-10-20T09:46:11", "2026-10-20T09:46:11"),
    "12.jpg": ("Film Scan 12 · 10/20/2026", "2026-10-20T09:46:12", "2026-10-20T09:46:12"),
    "14.jpg": ("Film Scan 14 · 10/20/2026", "2026-10-20T09:46:14", "2026-10-20T09:46:14"),
    "16.jpg": ("Film Scan 16 · 10/20/2026", "2026-10-20T09:46:16", "2026-10-20T09:46:16"),
    "17.jpg": ("Film Scan 17 · 10/20/2026", "2026-10-20T09:46:17", "2026-10-20T09:46:17"),
    "19.jpg": ("Film Scan 19 · 10/20/2026", "2026-10-20T09:46:19", "2026-10-20T09:46:19"),
    "20.jpg": ("Film Scan 20 · 10/20/2026", "2026-10-20T09:46:20", "2026-10-20T09:46:20"),
    "22.jpg": ("Film Scan 22 · 10/20/2026", "2026-10-20T09:46:22", "2026-10-20T09:46:22"),
    "23.jpg": ("Film Scan 23 · 10/20/2026", "2026-10-20T09:46:23", "2026-10-20T09:46:23"),
    "24.jpg": ("Film Scan 24 · 10/20/2026", "2026-10-20T09:46:24", "2026-10-20T09:46:24"),
    "25.jpg": ("Film Scan 25 · 10/20/2026", "2026-10-20T09:46:25", "2026-10-20T09:46:25"),
    "26.jpg": ("Film Scan 26 · 10/20/2026", "2026-10-20T09:46:26", "2026-10-20T09:46:26"),
    "27.jpg": ("Film Scan 27 · 10/20/2026", "2026-10-20T09:46:27", "2026-10-20T09:46:27"),
}


def natural_sort_key(filename):
    parts = re.split(r"(\d+)", filename.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def extract_exif_date(filepath):
    """Best-effort pure-Python scan for EXIF DateTimeOriginal / DateTime (YYYY:MM:DD HH:MM:SS)."""
    try:
        with open(filepath, "rb") as f:
            head = f.read(65536)
        m = re.search(rb"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})", head)
        if m:
            y, mo, d, hh, mm, ss = [x.decode("ascii") for x in m.groups()]
            if 1990 <= int(y) <= 2100 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                return f"{y}-{mo}-{d}T{hh}:{mm}:{ss}"
    except Exception:
        pass
    return None


def get_jpeg_dimensions(filepath):
    """Returns (width, height) accounting for JPEG SOF markers and EXIF Orientation."""
    width, height = 3000, 2000
    orientation = 1
    try:
        with open(filepath, "rb") as f:
            data = f.read(262144)
        i = 2
        n = len(data)
        while i < n - 1:
            if data[i] != 0xFF:
                i += 1
                continue
            while i < n and data[i] == 0xFF:
                i += 1
            if i >= n:
                break
            marker = data[i]
            i += 1
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7) or marker == 0x01:
                continue
            if i + 2 > n:
                break
            seg_len = struct.unpack(">H", data[i:i+2])[0]
            if seg_len < 2:
                break
            seg_data = data[i+2:i+seg_len]
            if marker == 0xE1 and seg_data.startswith(b"Exif\x00\x00"):
                tiff = seg_data[6:]
                if len(tiff) >= 8:
                    endian = "<" if tiff[:2] == b"II" else ">" if tiff[:2] == b"MM" else None
                    if endian:
                        ifd_offset = struct.unpack(endian + "I", tiff[4:8])[0]
                        if ifd_offset + 2 <= len(tiff):
                            num_entries = struct.unpack(endian + "H", tiff[ifd_offset:ifd_offset+2])[0]
                            for e in range(num_entries):
                                pos = ifd_offset + 2 + e * 12
                                if pos + 12 <= len(tiff):
                                    tag = struct.unpack(endian + "H", tiff[pos:pos+2])[0]
                                    if tag == 0x0112:
                                        orientation = struct.unpack(endian + "H", tiff[pos+8:pos+10])[0]
                                        break
            if marker in (0xC0, 0xC1, 0xC2) and len(seg_data) >= 5:
                h, w = struct.unpack(">HH", seg_data[1:5])
                if w > 0 and h > 0:
                    width, height = w, h
                    break
            i += seg_len
    except Exception:
        pass
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    return width, height


def make_title(filename, iso_date):
    stem = os.path.splitext(filename)[0]
    try:
        dt = datetime.datetime.fromisoformat(iso_date[:19])
        date_str = f"{dt.month}/{dt.day}/{dt.year}"
    except Exception:
        date_str = ""
    if stem.isdigit():
        label = f"Photo {stem}"
    else:
        label = stem.replace("_", " ").replace("-", " ").strip()
    return f"{label} · {date_str}" if date_str else label


def load_meta():
    if os.path.exists(META_FILE):
        try:
            with open(META_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    meta = {}
    for fname, (title, added, taken) in INITIAL_FILM_SCANS.items():
        meta[fname] = {"title": title, "added": added, "taken": taken}
    return meta


def sync_once():
    if not os.path.isdir(IMAGES_DIR):
        return False

    meta = load_meta()
    meta_changed = False

    for fname, (title, added, taken) in INITIAL_FILM_SCANS.items():
        if fname not in meta:
            meta[fname] = {"title": title, "added": added, "taken": taken}
            meta_changed = True

    files = [
        f for f in os.listdir(IMAGES_DIR)
        if not f.startswith(".") and f.lower().endswith((".jpg", ".jpeg"))
        and os.path.isfile(os.path.join(IMAGES_DIR, f))
    ]
    files.sort(key=natural_sort_key)
    file_set = set(files)

    # Prune deleted non-initial files from metadata so re-adding a test file gets a fresh added timestamp
    for k in list(meta.keys()):
        if k not in file_set and k not in INITIAL_FILM_SCANS:
            del meta[k]
            meta_changed = True

    entries = []
    for fname in files:
        fpath = os.path.join(IMAGES_DIR, fname)
        w, h = get_jpeg_dimensions(fpath)
        if fname in meta:
            info = meta[fname]
            if info.get("width") != w or info.get("height") != h:
                info["width"] = w
                info["height"] = h
                meta_changed = True
        else:
            now_dt = datetime.datetime.now()
            try:
                st = os.stat(fpath)
                mtime_dt = datetime.datetime.fromtimestamp(st.st_mtime)
                ctime_dt = datetime.datetime.fromtimestamp(st.st_ctime)
                added_dt = max(now_dt, ctime_dt, mtime_dt)
            except Exception:
                added_dt = now_dt
                mtime_dt = now_dt

            added_iso = added_dt.strftime("%Y-%m-%dT%H:%M:%S")
            taken_iso = extract_exif_date(fpath) or mtime_dt.strftime("%Y-%m-%dT%H:%M:%S")
            title = make_title(fname, added_iso)
            info = {"title": title, "added": added_iso, "taken": taken_iso, "width": w, "height": h}
            meta[fname] = info
            meta_changed = True

        entries.append({
            "file": "images/" + quote(fname),
            "name": fname,
            "title": info["title"],
            "added": info["added"],
            "taken": info["taken"],
            "width": info.get("width", w),
            "height": info.get("height", h),
        })

    if meta_changed or not os.path.exists(META_FILE):
        tmp_meta = META_FILE + ".tmp"
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp_meta, META_FILE)

    js_content = (
        "// Auto-generated from images/ folder — do not edit by hand\n"
        "window.__BULLETIN_MANIFEST__ = "
        + json.dumps(entries, indent=2, ensure_ascii=False)
        + ";\n"
    )

    existing_js = None
    if os.path.exists(MANIFEST_JS):
        try:
            with open(MANIFEST_JS, "r", encoding="utf-8") as f:
                existing_js = f.read()
        except Exception:
            pass

    if existing_js != js_content:
        tmp_js = MANIFEST_JS + ".tmp"
        with open(tmp_js, "w", encoding="utf-8") as f:
            f.write(js_content)
        os.replace(tmp_js, MANIFEST_JS)
        return True
    return False


def main():
    watch = "--watch" in sys.argv
    sync_once()
    if not watch:
        return

    last_sig = None
    while True:
        try:
            if os.path.isdir(IMAGES_DIR):
                sig_items = []
                for f in sorted(os.listdir(IMAGES_DIR)):
                    if not f.startswith(".") and f.lower().endswith((".jpg", ".jpeg")):
                        fp = os.path.join(IMAGES_DIR, f)
                        try:
                            sig_items.append((f, int(os.path.getmtime(fp)), os.path.getsize(fp)))
                        except Exception:
                            sig_items.append((f, 0, 0))
                sig = tuple(sig_items)
                if sig != last_sig:
                    sync_once()
                    last_sig = sig
        except Exception:
            pass
        time.sleep(0.4)


if __name__ == "__main__":
    main()
