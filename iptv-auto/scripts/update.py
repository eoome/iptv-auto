#!/usr/bin/env python3
"""
IPTV Source Auto-Updater
Fetches IPTV sources from multiple GitHub repos, validates them,
and generates M3U/TXT playlists separated by IPv4/IPv6.
"""

import json
import os
import re
import socket
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # repo root
SOURCES_FILE = SCRIPT_DIR / "sources.json"
TV_DIR = PROJECT_ROOT / "tv"
DOCS_DIR = PROJECT_ROOT / "docs"

# ── Helpers ──────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_url(url, timeout=10):
    """Fetch a URL and return its text content."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log(f"  ⚠ Failed to fetch {url}: {e}")
        return None


def is_ipv6(host):
    """Check if a hostname is an IPv6 address (no DNS lookup for speed)."""
    if not host:
        return False
    # Bracketed IPv6: [::1]
    if host.startswith("["):
        return True
    # Contains multiple colons = IPv6 literal
    if host.count(":") >= 2:
        return True
    # Known IPv6-only domains
    ipv6_indicators = ["ipv6", "6only", "ip6"]
    for indicator in ipv6_indicators:
        if indicator in host.lower():
            return True
    return False


def extract_host(url):
    """Extract hostname from URL."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return host.strip("[]")
    except Exception:
        return ""


# ── Parsing ──────────────────────────────────────────────────────────

def parse_m3u(text):
    """Parse M3U format, return list of (name, url) tuples."""
    entries = []
    lines = text.strip().splitlines()
    current_name = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            # Extract channel name after the last comma
            match = re.search(r',(.+)$', line)
            if match:
                current_name = match.group(1).strip()
        elif line.startswith("#"):
            continue
        elif line.startswith("http://") or line.startswith("https://"):
            name = current_name or "Unknown"
            entries.append((name, line))
            current_name = None

    return entries


def parse_txt(text):
    """Parse TXT format (name,url or name,#genre#)."""
    entries = []
    current_genre = ""

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if ",#genre#" in line:
            current_genre = line.split(",")[0].strip()
            continue

        if "," in line:
            parts = line.split(",", 1)
            name = parts[0].strip()
            url = parts[1].strip()
            if url.startswith("http://") or url.startswith("https://"):
                entries.append((name, url, current_genre))

    return entries


def parse_iptv_text(text, source_name=""):
    """Auto-detect format and parse."""
    text = text.strip()
    if text.startswith("#EXTM3U") or "#EXTINF:" in text:
        return parse_m3u(text)
    else:
        return parse_txt(text)


# ── Validation ───────────────────────────────────────────────────────

def validate_url(url, timeout=8):
    """
    Validate if a stream URL is playable.
    Checks: HTTP response + content type + actual data.
    For m3u8: verifies valid playlist content.
    For direct streams: verifies video/audio content type.
    """
    try:
        req = urllib.request.Request(url, method="GET", headers={
            "User-Agent": "Mozilla/5.0",
            "Range": "bytes=0-2048"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if status not in (200, 206, 301, 302):
                return False

            data = resp.read(2048)
            if len(data) < 16:
                return False

            content_type = resp.headers.get("Content-Type", "").lower()

            # m3u8 playlist check
            if ".m3u8" in url.lower() or "mpegurl" in content_type:
                text = data.decode("utf-8", errors="replace")
                if "#EXTM3U" in text or "#EXTINF" in text:
                    return True
                return False

            # Direct stream: accept video/audio content types
            if any(t in content_type for t in ["video", "audio", "octet-stream", "mpegts"]):
                return True

            # If content type is generic but we got enough data, accept it
            if len(data) >= 512:
                return True

            return False
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, OSError):
        pass
    except Exception:
        pass
    return False


def validate_stream(url, timeout=8, retry=1):
    """Validate with retry."""
    for attempt in range(retry + 1):
        if validate_url(url, timeout):
            return True
        if attempt < retry:
            time.sleep(1)
    return False


# ── Category detection ───────────────────────────────────────────────

def detect_category(name, config_categories):
    """Detect channel category based on name."""
    name_upper = name.upper()

    for cat, keywords in config_categories.items():
        for kw in keywords:
            if kw.upper() in name_upper:
                return cat

    return "其他"


# ── Main pipeline ────────────────────────────────────────────────────

def load_config():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def apply_proxy(url, proxy):
    """Apply GitHub proxy to raw.githubusercontent.com URLs."""
    if not proxy:
        return url
    if "raw.githubusercontent.com" in url:
        return proxy + url
    return url


def fetch_all_sources(config):
    """Fetch and parse all upstream sources."""
    all_entries = []  # (name, url, source_name, genre, ip_version)
    proxy = config.get("proxy", "")

    for source in config.get("upstream", []):
        name = source.get("name", "unknown")
        log(f"📥 Fetching from {name}...")
        for url in source.get("urls", []):
            fetch_url_final = apply_proxy(url, proxy)
            text = fetch_url(fetch_url_final)
            if text:
                # Detect IP version from source filename
                url_lower = url.lower()
                if "ipv6" in url_lower or "ip6" in url_lower:
                    ip_ver = "ipv6"
                elif "ipv4" in url_lower or "ip4" in url_lower:
                    ip_ver = "ipv4"
                else:
                    ip_ver = "auto"  # will detect per-URL

                entries = parse_iptv_text(text, name)
                for entry in entries:
                    if len(entry) == 2:
                        all_entries.append((entry[0], entry[1], name, "", ip_ver))
                    elif len(entry) == 3:
                        all_entries.append((entry[0], entry[1], name, entry[2], ip_ver))
                log(f"  ✓ Got {len(entries)} channels from {url.split('/')[-1]}")

    return all_entries


def deduplicate(entries):
    """Remove duplicate URLs, keep first occurrence."""
    seen_urls = set()
    seen_names = {}  # name -> first entry
    result = []

    for name, url, source, genre, ip_ver in entries:
        if url in seen_urls:
            continue
        seen_urls.add(url)

        key = f"{name}|{extract_host(url)}"
        if key in seen_names:
            continue
        seen_names[key] = True

        result.append((name, url, source, genre, ip_ver))

    return result


def validate_all(entries, config):
    """Validate all URLs concurrently."""
    validate_cfg = config.get("validate", {})
    timeout = validate_cfg.get("timeout", 8)
    max_workers = validate_cfg.get("max_workers", 30)
    retry = validate_cfg.get("retry", 1)

    log(f"🔍 Validating {len(entries)} channels (workers={max_workers}, timeout={timeout}s)...")

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_entry = {}
        for i, entry in enumerate(entries):
            url = entry[1]
            future = executor.submit(validate_url, url, timeout)
            future_to_entry[future] = i

        done_count = 0
        for future in as_completed(future_to_entry):
            idx = future_to_entry[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = False
            done_count += 1
            if done_count % 50 == 0:
                log(f"  ... validated {done_count}/{len(entries)}")

    valid = [entries[i] for i in range(len(entries)) if results.get(i, False)]
    log(f"✅ {len(valid)}/{len(entries)} channels are alive")
    return valid


def separate_ipv4_ipv6(entries):
    """Separate entries into IPv4 and IPv6 lists using source metadata + URL heuristic."""
    ipv4 = []
    ipv6 = []

    for name, url, source, genre, ip_ver in entries:
        if ip_ver == "ipv6":
            ipv6.append((name, url, source, genre))
        elif ip_ver == "ipv4":
            ipv4.append((name, url, source, genre))
        else:
            # Auto-detect from URL
            host = extract_host(url)
            if is_ipv6(host):
                ipv6.append((name, url, source, genre))
            else:
                ipv4.append((name, url, source, genre))

    return ipv4, ipv6


def categorize_entries(entries, config_categories):
    """Group entries by category."""
    categorized = {}
    for item in entries:
        name, url = item[0], item[1]
        genre = item[3] if len(item) > 3 else ""
        cat = genre if genre else detect_category(name, config_categories)
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append((name, url))

    return categorized


# ── Output generation ────────────────────────────────────────────────

def generate_txt(categorized, output_path):
    """Generate TXT format playlist."""
    lines = []
    for cat in categorized:
        lines.append(f"{cat},#genre#")
        for name, url in categorized[cat]:
            lines.append(f"{name},{url}")
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_m3u(categorized, output_path, title="IPTV"):
    """Generate M3U format playlist with EPG info."""
    lines = ['#!/usr/bin/env python3', '# -*- coding: utf-8 -*-', '']
    lines.append(f'#EXTM3U x-tvg-url="https://live.zbds.top/epg.xml"')
    lines.append(f'# Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')

    for cat in categorized:
        for name, url in categorized[cat]:
            lines.append(f'#EXTINF:-1 group-title="{cat}",{name}')
            lines.append(url)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_json(categorized, output_path):
    """Generate JSON format for web page consumption."""
    data = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": sum(len(v) for v in categorized.values()),
        "categories": {}
    }
    for cat, channels in categorized.items():
        data["categories"][cat] = [
            {"name": name, "url": url} for name, url in channels
        ]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    log("🚀 IPTV Auto-Updater starting...")

    config = load_config()
    categories = config.get("categories", {})

    # Fetch all sources
    all_entries = fetch_all_sources(config)
    if not all_entries:
        log("❌ No entries fetched, exiting")
        sys.exit(1)

    # Deduplicate
    all_entries = deduplicate(all_entries)
    log(f"📋 {len(all_entries)} unique channels after dedup")

    # Validate
    valid_entries = validate_all(all_entries, config)
    if not valid_entries:
        log("❌ No valid channels found, exiting")
        sys.exit(1)

    # Separate IPv4/IPv6
    ipv4, ipv6 = separate_ipv4_ipv6(valid_entries)
    log(f"📊 IPv4: {len(ipv4)} | IPv6: {len(ipv6)}")

    # Categorize
    ipv4_cat = categorize_entries(ipv4, categories)
    ipv6_cat = categorize_entries(ipv6, categories)

    # Ensure output dirs exist
    TV_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate files
    log("📝 Generating playlists...")

    generate_txt(ipv4_cat, TV_DIR / "iptv4.txt")
    generate_m3u(ipv4_cat, TV_DIR / "iptv4.m3u", "IPTV4")
    generate_txt(ipv6_cat, TV_DIR / "iptv6.txt")
    generate_m3u(ipv6_cat, TV_DIR / "iptv6.m3u", "IPTV6")

    # Also copy to docs/ for GitHub Pages
    generate_txt(ipv4_cat, DOCS_DIR / "iptv4.txt")
    generate_m3u(ipv4_cat, DOCS_DIR / "iptv4.m3u", "IPTV4")
    generate_txt(ipv6_cat, DOCS_DIR / "iptv6.txt")
    generate_m3u(ipv6_cat, DOCS_DIR / "iptv6.m3u", "IPTV6")

    # Generate JSON for web page
    all_cat = categorize_entries(valid_entries, categories)
    generate_json(all_cat, DOCS_DIR / "channels.json")
    generate_json(ipv4_cat, DOCS_DIR / "channels_ipv4.json")
    generate_json(ipv6_cat, DOCS_DIR / "channels_ipv6.json")

    log(f"✅ Done! Files written to {TV_DIR} and {DOCS_DIR}")
    log(f"   iptv4.txt / iptv4.m3u ({len(ipv4)} channels)")
    log(f"   iptv6.txt / iptv6.m3u ({len(ipv6)} channels)")


if __name__ == "__main__":
    main()
