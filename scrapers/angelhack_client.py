"""AngelHack event scraper using the site's WordPress event API."""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pipeline.domain_matcher import match_domains


API_URL = "https://angelhack.com/wp-json/wp/v2/event"
BASE_URL = "https://angelhack.com"
ARCHIVE_URL = "https://angelhack.com/events/"
PAGE_SIZE = 100
ACTIVE_STATUSES = {"event-status-ongoing", "event-status-upcoming"}


def fetch_angelhack_events() -> List[Dict[str, Any]]:
    """Fetch every WordPress event page using the API's total-page metadata."""
    records: List[Dict[str, Any]] = []
    page = 1
    total_pages: Optional[int] = None

    while total_pages is None or page <= total_pages:
        response = requests.get(
            API_URL,
            params={"page": page, "per_page": PAGE_SIZE},
            headers={
                "User-Agent": "Hackfolio/1.0",
                "Accept": "application/json",
                "Referer": "https://angelhack.com/events/",
            },
            timeout=30,
        )
        response.raise_for_status()
        page_records = response.json()
        if not isinstance(page_records, list):
            raise ValueError("AngelHack WordPress response is not a list")
        if total_pages is None:
            total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
            total = response.headers.get("X-WP-Total", "unknown")
            print(f"AngelHack API total: {total}; total pages: {total_pages}")
        print(f"  AngelHack page {page}: {len(page_records)} records")
        records.extend(page_records)
        if not page_records:
            break
        page += 1

    archive_metadata = _fetch_archive_metadata()
    for record in records:
        record["_archive_metadata"] = archive_metadata.get(record.get("link"), {})
    return records


def _fetch_archive_metadata() -> Dict[str, Dict[str, Any]]:
    response = requests.get(
        ARCHIVE_URL,
        headers={"User-Agent": "Hackfolio/1.0", "Accept": "text/html"},
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    metadata = {}
    date_pattern = re.compile(r"\b\d{2} [A-Z][a-z]{2} \d{4}\b", re.IGNORECASE)
    mode_pattern = re.compile(r"\b(Virtual|Hybrid|In-Person)\b", re.IGNORECASE)

    for card in soup.select("div.e-loop-item"):
        link = card.find("a", href=True)
        if not link:
            continue
        text = " ".join(card.get_text(" ", strip=True).split())
        dates = date_pattern.findall(text)
        mode_match = mode_pattern.search(text)
        if len(dates) < 2 or not mode_match:
            continue
        metadata[urljoin(BASE_URL, link["href"])] = {
            "event_start_date": _parse_archive_date(dates[0]),
            "event_end_date": _parse_archive_date(dates[1]),
            "mode": {"virtual": "online", "hybrid": "hybrid", "in-person": "offline"}[
                mode_match.group(1).lower()
            ],
            "location": text[mode_match.end():].strip() or None,
        }
    return metadata


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _parse_archive_date(value: str) -> Optional[str]:
    try:
        return datetime.strptime(value, "%d %b %Y").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def _rendered_text(record: Dict[str, Any]) -> str:
    rendered = ((record.get("content") or {}).get("rendered") or "")
    return " ".join(BeautifulSoup(rendered, "html.parser").get_text(" ", strip=True).split())


def _parse_prize(text: str) -> Dict[str, Any]:
    match = re.search(r"(?:US\$|USD\s*\$|\$|₹|EUR\s*€?)\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return {"amount": 0, "currency": "USD", "display_text": ""}
    symbol = match.group(0).lower()
    currency = "INR" if "₹" in symbol else "EUR" if "eur" in symbol else "USD"
    amount = float(match.group(1).replace(",", ""))
    return {"amount": amount, "currency": currency, "display_text": match.group(0)}


def normalize_angelhack(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only active/upcoming hackathons and normalize rendered fields."""
    hackathons = [
        event for event in raw_events
        if "event-type-hackathon" in event.get("class_list", [])
    ]
    active = [
        event for event in hackathons
        if ACTIVE_STATUSES.intersection(event.get("class_list", []))
    ]
    print(
        f"AngelHack filtering: {len(raw_events)} raw events -> "
        f"{len(hackathons)} hackathons -> {len(active)} active/upcoming hackathons"
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    normalized = []

    for event in active:
        text = _rendered_text(event)
        source_url = urljoin(BASE_URL, event.get("link") or "")
        archive = event.get("_archive_metadata") or {}
        normalized.append({
            "id": f"angelhack_{event.get('id', '')}",
            "title": BeautifulSoup(
                (event.get("title") or {}).get("rendered", ""), "html.parser"
            ).get_text(" ", strip=True),
            "organizer": "AngelHack",
            "source_platform": "angelhack",
            "source_url": source_url,
            "description": text,
            "domains": match_domains(text),
            "mode": archive.get("mode"),
            "location": archive.get("location"),
            "prize_pool": _parse_prize(text),
            "sponsors": [],
            "registration_deadline": None,  # Content has no reliable ISO registration deadline field.
            "event_start_date": archive.get("event_start_date"),
            "event_end_date": archive.get("event_end_date"),
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
    print("Fetching AngelHack events...")
    raw = fetch_angelhack_events()
    normalized = normalize_angelhack(raw)
    print(f"Normalized {len(normalized)} active/upcoming hackathons")
    with open("angelhack_raw.json", "w", encoding="utf-8") as output:
        json.dump(raw, output, indent=2)
    print("Saved raw response to angelhack_raw.json")
    if raw:
        print("\nSample raw response:")
        print(json.dumps(raw[0], indent=2))
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))


if __name__ == "__main__":
    main()