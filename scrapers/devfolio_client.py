"""Devfolio GraphQL client using the live hackathons-page query."""

import json
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.domain_matcher import match_domains


GRAPHQL_URL = "https://api.devfolio.co/v1/graphql"
PAGE_SIZE = 20
HACKATHON_FIELDS = """
    uuid slug name type starts_at ends_at is_online devfolio_official rating
    timezone participants_count participants_details
    themes { theme { name } }
    settings { reg_ends_at reg_starts_at review site external_apply_url }
"""


def _request(query: str, offset: int) -> Dict[str, Any]:
    body = json.dumps({
        "query": query,
        "variables": {"offset": offset, "limit": PAGE_SIZE},
    }).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Hackfolio/1.0"},
        method="POST",
    )
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"Devfolio GraphQL error: {payload['errors']}")
    return payload.get("data", {})


def _query(category: str) -> str:
    if category == "open_hackathons":
        predicate = """{
            _and: [
                { private: { _eq: false } }
                { settings: { reg_starts_at: { _lte: now }, reg_ends_at: { _gte: now } } }
            ]
        }"""
        order = "{ settings: { reg_ends_at: asc } }"
    else:
        predicate = """{
            _and: [
                { private: { _eq: false } }
                { settings: { reg_starts_at: { _gte: now } } }
            ]
        }"""
        order = "{ settings: { reg_starts_at: asc } }"
    return f"""
        query DevfolioHackathons($offset: Int!, $limit: Int!) {{
            {category}: hackathons(
                where: {predicate}
                limit: $limit offset: $offset order_by: {order}
            ) {{ {HACKATHON_FIELDS} }}
        }}
    """


def fetch_devfolio_hackathons() -> List[Dict[str, Any]]:
    """Fetch every open/upcoming page until the API returns an empty page."""
    records: List[Dict[str, Any]] = []
    seen_ids = set()
    for category in ("open_hackathons", "upcoming_hackathons"):
        offset = 0
        while True:
            page = _request(_query(category), offset).get(category, [])
            print(f"  Devfolio {category}: offset {offset}, {len(page)} records")
            if not page:
                break
            for record in page:
                record_id = record.get("uuid") or record.get("slug")
                if record_id and record_id not in seen_ids:
                    seen_ids.add(record_id)
                    records.append(record)
            offset += len(page)
            time.sleep(0.1)
    return records


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _is_current(record: Dict[str, Any], now: datetime) -> bool:
    settings = record.get("settings") or {}
    registration_end = _parse_date(settings.get("reg_ends_at"))
    event_end = _parse_date(record.get("ends_at"))
    end_value = registration_end or event_end
    end_dt = datetime.fromisoformat(end_value) if end_value else None
    # The API already separates open and upcoming records. Locally, only
    # discard records whose known registration/event window has ended.
    return end_dt is None or end_dt >= now


def normalize_devfolio(raw_hackathons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter current records and normalize fields verified in the live query."""
    now = datetime.now(timezone.utc)
    current = [record for record in raw_hackathons if _is_current(record, now)]
    print(f"Devfolio filtering: {len(raw_hackathons)} raw candidates -> {len(current)} current events")
    timestamp = now.isoformat()
    normalized = []
    for record in current:
        settings = record.get("settings") or {}
        domains = []
        for theme in record.get("themes") or []:
            name = ((theme.get("theme") or {}).get("name") or "")
            for domain in match_domains(name):
                if domain not in domains:
                    domains.append(domain)
        online = record.get("is_online")
        mode = "online" if online is True else "offline" if online is False else None
        slug = record.get("slug")
        normalized.append({
            "id": f"devfolio_{record.get('uuid', '')}",
            "title": record.get("name", ""),
            "organizer": "Devfolio Community",  # No organizer field exists in this query.
            "source_platform": "devfolio",
            "source_url": f"https://devfolio.co/hackathons/{slug}" if slug else None,
            "description": "",  # Description is not exposed by the listing query.
            "domains": domains,
            "mode": mode,
            "location": None,  # timezone is not a geographic location.
            "prize_pool": {  # Prize data is not exposed by the listing query.
                "amount": 0,
                "currency": "USD",
                "display_text": "",
            },
            "sponsors": [],  # Sponsor data is not exposed by the listing query.
            "registration_deadline": _parse_date(settings.get("reg_ends_at")),
            "event_start_date": _parse_date(record.get("starts_at")),
            "event_end_date": _parse_date(record.get("ends_at")),
            "participant_count": record.get("participants_count"),
            "impact_score": 0,
            "score_breakdown": {key: 0 for key in (
                "organizer_tier", "sponsor_recognition", "prize_pool",
                "domain_match", "participation_scale", "recency"
            )},
            "tags": [record["type"]] if record.get("type") else [],
            "is_mlh_sanctioned": False,
            "ingested_at": timestamp,
            "last_updated_at": timestamp,
        })
    return normalized


def main() -> None:
    print("Fetching Devfolio hackathons...")
    raw = fetch_devfolio_hackathons()
    print(f"Fetched {len(raw)} raw active/upcoming candidates")
    normalized = normalize_devfolio(raw)
    print(f"Normalized {len(normalized)} current hackathons")
    with open("devfolio_raw.json", "w", encoding="utf-8") as output:
        json.dump(raw, output, indent=2)
    print("Saved raw response to devfolio_raw.json")
    if raw:
        print("\nSample raw response:")
        print(json.dumps(raw[0], indent=2))
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))


if __name__ == "__main__":
    main()