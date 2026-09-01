"""Unstop Playwright scraper for scheduled ingestion.

Unstop is a JavaScript SPA. The browser-observed JSON endpoint is used through
Playwright's browser context so the SPA session and anti-bot behavior remain
visible. This client is intentionally not called from FastAPI startup; the
browser cost belongs in scheduled ingestion.

Setup requires both ``pip install -r requirements.txt`` and the separate
``venv314\\Scripts\\python.exe -m playwright install chromium`` command.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

try:
    from pipeline.domain_matcher import match_domains
except ModuleNotFoundError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from pipeline.domain_matcher import match_domains


UNSTOP_URL = "https://unstop.com/hackathons"
SEARCH_URL = "https://unstop.com/api/public/opportunity/search-result"
PAGE_SIZE = 18
BLOCK_MARKERS = (
    "verify you are human",
    "cf-chl-",
    "access denied",
    "just a moment...",
)
LOGGER = logging.getLogger(__name__)


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _is_blocked(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in BLOCK_MARKERS)


def fetch_unstop_hackathons() -> List[Dict[str, Any]]:
    """Fetch all records returned by Unstop's own open-hackathons filter."""
    records: List[Dict[str, Any]] = []
    seen_ids = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Hackfolio/1.0")
        page = context.new_page()
        response = page.goto(UNSTOP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        body_text = page.locator("body").inner_text()
        if response and response.status >= 400:
            raise RuntimeError(f"Unstop page returned HTTP {response.status}")
        if _is_blocked(body_text):
            raise RuntimeError("Unstop anti-bot challenge detected; ingestion stopped")

        page_number = 1
        total = None
        last_page = None
        while True:
            api_response = context.request.get(
                SEARCH_URL,
                params={
                    "opportunity": "hackathons",
                    "page": page_number,
                    "per_page": PAGE_SIZE,
                    "oppstatus": "open",
                    "undefined": "true",
                },
                timeout=60000,
            )
            if api_response.status >= 400:
                raise RuntimeError(f"Unstop API returned HTTP {api_response.status}")
            payload = api_response.json()
            data = payload.get("data") or {}
            page_records = data.get("data") or []
            total = data.get("total", total)
            last_page = data.get("last_page", last_page)
            print(
                f"  Unstop page {page_number}: {len(page_records)} records; "
                f"next={bool(data.get('next_page_url'))}"
            )
            for record in page_records:
                record_id = record.get("id")
                if record_id not in seen_ids:
                    seen_ids.add(record_id)
                    records.append(record)
            if not page_records or not data.get("next_page_url"):
                break
            page_number += 1

        print(f"Unstop API metadata: total={total}, last_page={last_page}, collected={len(records)}")
        if total is not None and total != len(records):
            print(f"WARNING: Unstop reports {total} records but returned {len(records)} unique records")
        browser.close()
    return records


def _parse_prize(record: Dict[str, Any]) -> Dict[str, Any]:
    prizes = record.get("prizes") or []
    if not prizes:
        return {"amount": 0, "currency": "INR", "display_text": ""}
    prize = prizes[0]
    amount = prize.get("cash") or prize.get("max_cash") or 0
    currency_code = (prize.get("currencyCode") or "").upper()
    currency_name = (prize.get("currency") or "").lower()
    if currency_name == "fa-rupee":
        currency_code = "INR"
    elif currency_name == "fa-dollar":
        currency_code = "USD"
    if not currency_code:
        LOGGER.warning(
            "Unstop prize has unrecognized currency marker %r; using neutral scoring.",
            prize.get("currency"),
        )
        currency_code = "UNKNOWN"
    currency = currency_code
    return {
        "amount": amount,
        "currency": currency,
        "display_text": f"{amount:g} {currency}" if amount else "",
    }


def _description(record: Dict[str, Any]) -> str:
    return " ".join(
        BeautifulSoup(record.get("details") or "", "html.parser")
        .get_text(" ", strip=True)
        .split()
    )


def _mode(description: str) -> Optional[str]:
    match = re.search(r"\bmode\s*:\s*(online|offline|hybrid)\b", description, re.IGNORECASE)
    return match.group(1).lower() if match else None


def normalize_unstop(raw_hackathons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep Unstop's live records and normalize verified fields."""
    hackathons = [record for record in raw_hackathons if record.get("type") == "hackathons"]
    active = [record for record in hackathons if record.get("status") == "LIVE"]
    print(
        f"Unstop filtering: {len(raw_hackathons)} raw records -> "
        f"{len(hackathons)} hackathons -> {len(active)} LIVE events"
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    normalized = []
    for record in active:
        description = _description(record)
        organization = record.get("organisation") or {}
        address = record.get("address_with_country_logo") or {}
        country = address.get("country") or {}
        location = ", ".join(
            part for part in (address.get("city"), address.get("state"), country.get("name")) if part
        ) or None
        source_url = urljoin("https://unstop.com/", record.get("public_url") or "")
        text = " ".join([
            record.get("title") or "",
            description,
            " ".join(tag.get("name", "") if isinstance(tag, dict) else str(tag) for tag in record.get("tags") or []),
            " ".join(skill.get("skill_name", "") for skill in record.get("required_skills") or []),
        ])
        normalized.append({
            "id": f"unstop_{record.get('id', '')}",
            "title": record.get("title", ""),
            "organizer": organization.get("name", "") if isinstance(organization, dict) else "",
            "source_platform": "unstop",
            "source_url": source_url,
            "description": description,
            "domains": match_domains(text),
            "mode": _mode(description),
            "location": location,
            "prize_pool": _parse_prize(record),
            "sponsors": [],
            "registration_deadline": _parse_date(record.get("end_date")),
            "event_start_date": None,  # No structured start date is present in this response.
            "event_end_date": _parse_date(record.get("end_date")),
            "participant_count": record.get("registerCount"),
            "impact_score": 0,
            "score_breakdown": {key: 0 for key in (
                "organizer_tier", "sponsor_recognition", "prize_pool",
                "domain_match", "participation_scale", "recency"
            )},
            "tags": [record["subtype"]] if record.get("subtype") else [],
            "is_mlh_sanctioned": False,
            "ingested_at": timestamp,
            "last_updated_at": timestamp,
        })
    return normalized


def main() -> None:
    print("Fetching Unstop hackathons with Playwright...")
    raw = fetch_unstop_hackathons()
    normalized = normalize_unstop(raw)
    print(f"Normalized {len(normalized)} live hackathons")
    with open("unstop_raw.json", "w", encoding="utf-8") as output:
        json.dump(raw, output, indent=2)
    print("Saved raw response to unstop_raw.json")
    if raw:
        print("\nSample raw response:")
        print(json.dumps(raw[0], indent=2))
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))


if __name__ == "__main__":
    main()