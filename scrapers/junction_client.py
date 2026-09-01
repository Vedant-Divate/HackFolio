"""Junction platform API client."""

import json
import re
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

try:
    from pipeline.domain_matcher import match_domains
except ModuleNotFoundError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from pipeline.domain_matcher import match_domains


TRPC_URL = "https://hackjunction.app/api/trpc"
PLATFORM_URL = "https://hackjunction.app/hackathons"


def _fetch_procedure(name: str) -> List[Dict[str, Any]]:
    response = requests.get(
        f"{TRPC_URL}/{name}",
        headers={"User-Agent": "Hackfolio/1.0", "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    try:
        records = payload["result"]["data"]["json"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Unexpected Junction response for {name}") from error
    if not isinstance(records, list):
        raise ValueError(f"Junction response for {name} is not a list")
    return records


def fetch_junction_events() -> List[Dict[str, Any]]:
    """Fetch future and past records, which are complete non-overlapping API sets."""
    records = []
    seen_ids = set()
    for procedure in ("event.getAllFutureEvents", "event.getAllPastEvents"):
        page = _fetch_procedure(procedure)
        print(f"  Junction {procedure}: {len(page)} records")
        for record in page:
            if record.get("id") not in seen_ids:
                seen_ids.add(record.get("id"))
                records.append(record)
    return records


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _is_current(record: Dict[str, Any], now: datetime) -> bool:
    end = _parse_date(record.get("endTime"))
    return end is not None and datetime.fromisoformat(end) >= now


def _parse_prize(text: str) -> Dict[str, Any]:
    match = re.search(
        r"(?:(US\$|USD\s*\$|\$|₹|EUR\s*€?|JPY\s*¥?|¥)\s*([\d,]+(?:\.\d+)?)|"
        r"([\d,]+(?:\.\d+)?)\s*(USD|EUR|JPY|INR))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return {"amount": 0, "currency": "EUR", "display_text": ""}
    display_text = match.group(0)
    amount_text = match.group(2) or match.group(3)
    currency_text = (match.group(1) or match.group(4) or "EUR").upper()
    currency = "INR" if "₹" in currency_text else currency_text.replace("$", "")
    if currency in {"US", "USD"}:
        currency = "USD"
    elif currency not in {"EUR", "JPY", "INR"}:
        currency = "EUR"
    return {"amount": float(amount_text.replace(",", "")), "currency": currency, "display_text": display_text}


def normalize_junction(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter ended events and normalize Junction's verified fields."""
    now = datetime.now(timezone.utc)
    current = [record for record in raw_events if _is_current(record, now)]
    print(f"Junction filtering: {len(raw_events)} raw records -> {len(current)} current/upcoming events")
    timestamp = now.isoformat()
    normalized = []
    for record in current:
        event_type = record.get("eventType")
        mode = {"online": "online", "physical": "offline"}.get(event_type)
        normalized.append({
            "id": f"junction_{record.get('id', '')}",
            "title": record.get("name", ""),
            "organizer": "Junction",  # The API exposes no separate organizer name.
            "source_platform": "junction",
            "source_url": f"{PLATFORM_URL}/{record.get('slug', '')}",
            "description": record.get("description") or "",
            "domains": match_domains(record.get("description") or ""),
            "mode": mode,
            "location": None,  # The API exposes a timezone, not a geographic venue field.
            "prize_pool": {
                "amount": 0,
                "currency": "EUR",
                "display_text": "",
            } if not record.get("description") else _parse_prize(record["description"]),
            "sponsors": [],
            "registration_deadline": _parse_date(record.get("registrationEndTime")),
            "event_start_date": _parse_date(record.get("startTime")),
            "event_end_date": _parse_date(record.get("endTime")),
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
    print("Fetching Junction events...")
    raw = fetch_junction_events()
    normalized = normalize_junction(raw)
    print(f"Normalized {len(normalized)} current/upcoming events")
    with open("junction_raw.json", "w", encoding="utf-8") as output:
        json.dump(raw, output, indent=2)
    print("Saved raw response to junction_raw.json")
    if raw:
        print("\nSample raw response:")
        print(json.dumps(raw[0], indent=2))
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))


if __name__ == "__main__":
    main()