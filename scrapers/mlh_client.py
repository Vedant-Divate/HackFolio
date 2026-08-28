"""
MLH (Major League Hacking) Scraper Client
Implements section 11 (Phase 1) and section 4.1 for MLH.
Access method: JSON feed embedded in the season page (Inertia.js payload).
Normalizes data to the unified schema defined in section 7.

Notes on field availability (verified against live payload 2026-08-28):
- description/tagline: not present in the feed.
- sponsors: no per-event sponsor/host field exists; 'organizer' defaults to "MLH".
- prize_pool: not present in the feed.
- registration_deadline: not present; left null (distinct from event start date).
- formatType values: 'physical', 'digital', 'hybrid_physical' — all three handled.
- domains: no theme/category field exists; left as empty array.
"""
import urllib.request
import ssl
import json
import re
import uuid
from datetime import datetime, timezone

SEASON_URL = "https://mlh.io/seasons/2026/events"


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_mlh_events():
    """Fetch and return raw MLH event dicts from the Inertia.js page payload."""
    try:
        req = urllib.request.Request(
            SEASON_URL,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        html = urllib.request.urlopen(req, context=_ssl_ctx()).read().decode("utf-8")
        match = re.search(
            r'<script data-page="app" type="application/json">(.*?)</script>',
            html,
            re.DOTALL
        )
        if not match:
            print("MLH: could not locate Inertia page payload in HTML.")
            return []
        data = json.loads(match.group(1))
        props = data.get("props", {})
        upcoming = props.get("upcomingEvents", [])
        past = props.get("pastEvents", [])
        return upcoming + past
    except Exception as e:
        print(f"Error fetching from MLH: {e}")
        return []


def _map_format(format_type):
    """
    Map MLH's formatType to unified mode.
    Confirmed live values: 'physical', 'digital', 'hybrid_physical'.
    """
    mapping = {
        "physical": "offline",
        "digital": "online",
        "hybrid_physical": "hybrid",
    }
    return mapping.get(format_type, "online")   # safe default for unknown future values


def normalize_mlh(raw_events):
    """Normalize raw MLH event dicts into the section-7 unified schema."""
    normalized = []
    now = datetime.now(timezone.utc).isoformat()

    for h in raw_events:
        format_type = h.get("formatType", "digital")
        mode = _map_format(format_type)

        # Build location string from venueAddress if present
        venue = h.get("venueAddress") or {}
        location_parts = [venue.get("city"), venue.get("state"), venue.get("country")]
        location_str = h.get("location") or ", ".join(p for p in location_parts if p) or None
        if mode == "online":
            location_str = None

        # source_url: prefer websiteUrl (external hackathon site), fall back to mlh.io relative url
        website = h.get("websiteUrl") or ""
        mlh_path = h.get("url") or ""
        source_url = website if website else f"https://mlh.io{mlh_path}"

        normalized_item = {
            "id": str(uuid.uuid4()),
            "title": h.get("name", ""),
            "organizer": "MLH",          # no per-event host field exists in payload (verified)
            "source_platform": "mlh",
            "source_url": source_url,
            "description": "",           # not present in MLH feed (verified)
            "domains": [],               # no theme/category field in MLH feed (verified)
            "mode": mode,
            "location": location_str,
            "prize_pool": {              # not present in MLH feed (verified)
                "amount": 0,
                "currency": "USD",
                "display_text": ""
            },
            "sponsors": [],              # no per-event sponsor field in MLH feed (verified)
            "registration_deadline": None,   # not in feed; intentionally null (per spec review)
            "event_start_date": h.get("startsAt"),
            "event_end_date": h.get("endsAt"),
            "participant_count": None,   # not in feed
            "impact_score": 0,
            "score_breakdown": {
                "organizer_tier": 0,
                "sponsor_recognition": 0,
                "prize_pool": 0,
                "domain_match": 0,
                "participation_scale": 0,
                "recency": 0
            },
            "tags": [h.get("region", "")] if h.get("region") else [],
            "is_mlh_sanctioned": True,   # by definition — everything from this feed is MLH-sanctioned
            "ingested_at": now,
            "last_updated_at": now,
        }
        normalized.append(normalized_item)

    return normalized


if __name__ == "__main__":
    print("Fetching MLH events...")
    raw = fetch_mlh_events()
    print(f"Fetched {len(raw)} events (upcoming + past).")

    normalized = normalize_mlh(raw)

    with open("mlh_raw.json", "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)

    print("Saved to mlh_raw.json")
    if normalized:
        # Show first upcoming event if any, otherwise first past
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))
