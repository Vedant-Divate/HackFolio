"""Hackathon.com HTML scraper for the DevNetwork source."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from pipeline.domain_matcher import match_domains
except ModuleNotFoundError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from pipeline.domain_matcher import match_domains


HOME_URL = "https://www.hackathon.com/"
BASE_URL = "https://www.hackathon.com"


def fetch_devnetwork_events() -> List[Dict[str, Any]]:
    """Fetch every event card exposed on Hackathon.com's homepage.

    The site exposes no total-count or pagination metadata. Its numbered routes
    repeat the homepage, so there is no evidence of an additional page to walk.
    """
    response = requests.get(HOME_URL, headers={"User-Agent": "Hackfolio/1.0"}, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    records = []
    seen_urls = set()

    for card in soup.select("div.hero"):
        title_link = card.select_one("a.hero__title[href]")
        if not title_link:
            continue
        source_url = urljoin(BASE_URL, title_link["href"])
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        topics = [link.get_text(" ", strip=True) for link in card.select("a.ht-event-topics__tag")]
        detail = _fetch_detail(source_url)
        records.append({
            "title": title_link.get_text(" ", strip=True),
            "source_url": source_url,
            "topics": topics,
            "detail": detail,
        })
    return records


def _fetch_detail(url: str) -> Dict[str, Any]:
    response = requests.get(url, headers={"User-Agent": "Hackfolio/1.0"}, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    event_data = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            candidate = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue
        candidates = candidate if isinstance(candidate, list) else [candidate]
        event_data = next(
            (item for item in candidates if isinstance(item, dict) and item.get("@type") == "Event"),
            event_data,
        )
    description = soup.find("meta", attrs={"name": "description"})
    return {
        "schema": event_data,
        "description": description.get("content", "").strip() if description else "",
    }


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _parse_prize(text: str) -> Dict[str, Any]:
    match = re.search(r"(?:US\$|USD\s*\$|\$|₹|EUR\s*€?)\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return {"amount": 0, "currency": "USD", "display_text": ""}
    symbol = match.group(0).lower()
    currency = "INR" if "₹" in symbol else "EUR" if "eur" in symbol else "USD"
    return {"amount": float(match.group(1).replace(",", "")), "currency": currency, "display_text": match.group(0)}


def _is_current(record: Dict[str, Any], now: datetime) -> bool:
    end = _parse_date(((record.get("detail") or {}).get("schema") or {}).get("endDate"))
    return end is not None and datetime.fromisoformat(end) >= now


def normalize_devnetwork(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter ended homepage cards and normalize detail-page JSON-LD fields."""
    now = datetime.now(timezone.utc)
    current = [record for record in raw_events if _is_current(record, now)]
    print(f"DevNetwork filtering: {len(raw_events)} homepage cards -> {len(current)} current events")
    timestamp = now.isoformat()
    normalized = []
    for record in current:
        detail = record.get("detail") or {}
        schema = detail.get("schema") or {}
        description = detail.get("description") or ""
        attendance = schema.get("eventAttendanceMode") or ""
        topics = record.get("topics") or []
        mode = (
            "online" if "Online" in attendance or "Virtual" in topics
            else "offline" if "Offline" in attendance or "InPerson" in attendance
            else "hybrid" if "Mixed" in attendance
            else None
        )
        location = schema.get("location")
        if isinstance(location, dict):
            location = location.get("name") or location.get("address")
        if isinstance(location, dict):
            location = ", ".join(str(value) for value in location.values() if value)
        text = f"{record.get('title', '')} {' '.join(record.get('topics') or [])} {description}"
        organizer = schema.get("organizer")
        organizer = organizer.get("name", "") if isinstance(organizer, dict) else organizer or ""
        normalized.append({
            "id": f"devnetwork_{record['source_url'].rstrip('/').split('/')[-1]}",
            "title": record.get("title", ""),
            "organizer": organizer,
            "source_platform": "devnetwork",
            "source_url": record["source_url"],
            "description": description,
            "domains": match_domains(text),
            "mode": mode,
            "location": location,
            "prize_pool": _parse_prize(description),
            "sponsors": [],
            "registration_deadline": None,
            "event_start_date": _parse_date(schema.get("startDate")),
            "event_end_date": _parse_date(schema.get("endDate")),
            "participant_count": None,
            "impact_score": 0,
            "score_breakdown": {key: 0 for key in (
                "organizer_tier", "sponsor_recognition", "prize_pool",
                "domain_match", "participation_scale", "recency"
            )},
            "tags": ["hackathon"],
            "is_mlh_sanctioned": False,
            "ingested_at": timestamp,
            "last_updated_at": timestamp,
        })
    return normalized


def main() -> None:
    print("Fetching DevNetwork/Hackathon.com events...")
    raw = fetch_devnetwork_events()
    normalized = normalize_devnetwork(raw)
    print(f"Normalized {len(normalized)} current events")
    with open("devnetwork_raw.json", "w", encoding="utf-8") as output:
        json.dump(raw, output, indent=2)
    print("Saved raw response to devnetwork_raw.json")
    if raw:
        print("\nSample raw response:")
        print(json.dumps(raw[0], indent=2))
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))


if __name__ == "__main__":
    main()