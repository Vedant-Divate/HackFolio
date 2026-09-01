"""HackerEarth challenge scraper.

HackerEarth's current challenges page is a JavaScript shell. Its live client
loads the JSON listing endpoint below; challenge pages are HTML and are parsed
with BeautifulSoup for metadata that is available there.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pipeline.domain_matcher import match_domains


LISTING_URL = "https://www.hackerearth.com/api/community/challenges/compete/"
BASE_URL = "https://www.hackerearth.com"


def fetch_hackerearth_challenges() -> List[Dict[str, Any]]:
    """Fetch HackerEarth's complete listing response.

    The endpoint provides one response and no pagination or total-count field;
    pagination is therefore not applicable. Historical records are filtered
    in normalize_hackerearth using the verified end timestamp.
    """
    response = requests.get(
        LISTING_URL,
        headers={"User-Agent": "Hackfolio/1.0", "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    records = payload.get("data", [])
    if not isinstance(records, list):
        raise ValueError("HackerEarth response data is not a list")
    return records


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
            tzinfo=timezone.utc
        ).isoformat()
    except ValueError:
        return None


def _detail_description(url: str) -> str:
    """Read an HTML description when the challenge page exposes one."""
    response = requests.get(url, headers={"User-Agent": "Hackfolio/1.0"}, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    description = soup.find("meta", attrs={"name": "description"})
    return (description.get("content") or "").strip() if description else ""


def _is_current(record: Dict[str, Any], now: datetime) -> bool:
    end = _parse_date(record.get("end"))
    return end is not None and datetime.fromisoformat(end) >= now


def normalize_hackerearth(raw_challenges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter ended challenges and normalize verified HackerEarth fields."""
    now = datetime.now(timezone.utc)
    hackathons = [record for record in raw_challenges if record.get("type") == "Hackathon"]
    current = [record for record in hackathons if _is_current(record, now)]
    print(
        f"HackerEarth filtering: {len(raw_challenges)} raw records -> "
        f"{len(hackathons)} hackathons -> {len(current)} current events"
    )
    timestamp = now.isoformat()
    normalized = []

    for record in current:
        relative_url = record.get("url") or ""
        source_url = urljoin(BASE_URL, relative_url)
        description = ""
        try:
            description = _detail_description(source_url)
        except requests.RequestException as error:
            print(f"  Could not fetch detail page for {record.get('slug')}: {error}")

        normalized.append({
            "id": f"hackerearth_{record.get('slug', '')}",
            "title": record.get("title", ""),
            "organizer": record.get("company_name") or "",
            "source_platform": "hackerearth",
            "source_url": source_url,
            "description": description,
            "domains": match_domains(description),
            "mode": None,  # No online/offline field is exposed by the verified response.
            "location": None,
            "prize_pool": {
                "amount": 0,
                "currency": "USD",
                "display_text": "",
            },  # Prize data is absent from the listing response.
            "sponsors": [],
            "registration_deadline": None,  # HackerEarth exposes challenge end, not registration end.
            "event_start_date": _parse_date(record.get("start")),
            "event_end_date": _parse_date(record.get("end")),
            "participant_count": record.get("subscription_count"),
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
    print("Fetching HackerEarth challenges...")
    raw = fetch_hackerearth_challenges()
    print(f"Fetched {len(raw)} raw records")
    normalized = normalize_hackerearth(raw)
    print(f"Normalized {len(normalized)} current challenges")
    with open("hackerearth_raw.json", "w", encoding="utf-8") as output:
        json.dump(raw, output, indent=2)
    print("Saved raw response to hackerearth_raw.json")
    if raw:
        print("\nSample raw response:")
        print(json.dumps(raw[0], indent=2))
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))


if __name__ == "__main__":
    main()