#!/usr/bin/env python3
"""Check the UAD (Universite Arastirmalari Dergisi) DergiPark page for signs
that article submission has opened, and record the result in state.json so a
separate process can decide whether to notify anyone.

No third-party dependencies: only the standard library, so it runs on a
plain GitHub Actions ubuntu runner with no pip install step.
"""
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://dergipark.org.tr/tr/pub/uad"
STATE_PATH = Path(__file__).parent / "state.json"

# The page's header shows an authoritative current-status line, e.g.
# "Makale Gönderimine Açık" / "Makale Gönderimine Kapalı" (adjective forms:
# "open"/"closed"). The page ALSO embeds a submission history log further
# down ("Gönderime Açıldı 27.08.2026...", "Gönderime Kapandı 23.08.2026...",
# using verb-past forms: "opened"/"closed [at a point in time]") that lists
# every past transition -- so it always contains both "opened" and "closed"
# entries regardless of the current state. Matching the verb forms as a
# signal is therefore useless (always true); only the adjective-form header
# reliably reflects the current state.
AUTHORITATIVE_OPEN_PHRASES = [
    "gönderimine açık",
]
AUTHORITATIVE_CLOSED_PHRASES = [
    "gönderimine kapalı",
]

# Weaker, generic phrases kept as a fallback in case the exact header
# wording changes -- these are heuristics, not guarantees.
GENERIC_OPEN_PHRASES = [
    "gönderime açık",
    "gönderilere açık",
    "gönderiye açık",
    "yeni makale gönderimi",
    "makale gönderimi başlamıştır",
    "başvurular açılmıştır",
    "başvurular başlamıştır",
    "makale kabul edilmektedir",
    "makale çağrısı",
    "call for papers",
    "submissions are open",
    "submission is open",
    "now accepting",
]

GENERIC_CLOSED_PHRASES = [
    "gönderime kapalı",
    "gönderim kapalıdır",
    "makale kabul etmemektedir",
    "makale kabul edilmemektedir",
    "gönderim tarihleri sona ermiştir",
    "başvurular sona ermiştir",
    "not currently accepting",
    "submissions are closed",
    "closed for submission",
]


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_matches(text: str, phrases: list[str]) -> list[str]:
    lowered = text.lower()
    return [p for p in phrases if p in lowered]


def load_previous_state() -> dict | None:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            return None
    return None


def main() -> int:
    try:
        text = fetch_text(URL)
    except Exception as exc:  # network/DNS/HTTP errors on the runner
        print(f"fetch failed: {exc}", file=sys.stderr)
        state = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "url": URL,
            "fetch_error": str(exc),
        }
        STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
        return 1

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    auth_open = find_matches(text, AUTHORITATIVE_OPEN_PHRASES)
    auth_closed = find_matches(text, AUTHORITATIVE_CLOSED_PHRASES)
    open_matches = auth_open + find_matches(text, GENERIC_OPEN_PHRASES)
    closed_matches = auth_closed + find_matches(text, GENERIC_CLOSED_PHRASES)

    if auth_open:
        likely_open = True
    elif auth_closed:
        likely_open = False
    elif open_matches and not closed_matches:
        likely_open = True
    elif closed_matches and not open_matches:
        likely_open = False
    elif open_matches and closed_matches:
        likely_open = True  # ambiguous but lean toward alerting, not missing it
    else:
        likely_open = None  # unknown -- no phrase matched either way

    previous = load_previous_state()
    previous_hash = previous.get("content_hash") if previous else None
    previous_likely_open = previous.get("likely_open") if previous else None
    changed = content_hash != previous_hash

    # "just_opened" is the edge-trigger the notifier cares about: it stays
    # True only for the run where the state actually flips to open, so a
    # 10-hourly poller does not re-notify every single run while it stays
    # open.
    just_opened = bool(likely_open) and previous_likely_open is not True

    excerpt_source = text
    if auth_open or auth_closed:
        anchor = (auth_open + auth_closed)[0]
        idx = text.lower().find(anchor)
        excerpt_source = text[max(0, idx - 200) : idx + 400]
    elif open_matches:
        idx = text.lower().find(open_matches[0])
        excerpt_source = text[max(0, idx - 200) : idx + 400]
    elif closed_matches:
        idx = text.lower().find(closed_matches[0])
        excerpt_source = text[max(0, idx - 200) : idx + 400]
    excerpt = excerpt_source[:800]

    state = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "url": URL,
        "content_hash": content_hash,
        "likely_open": likely_open,
        "matched_open_phrases": open_matches,
        "matched_closed_phrases": closed_matches,
        "changed_since_last_check": changed,
        "just_opened": just_opened,
        "excerpt": excerpt,
    }
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
