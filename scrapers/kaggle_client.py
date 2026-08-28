"""
Kaggle Scraper Client
Implements section 11 (Phase 1) and section 4.1 for Kaggle.
Access method: Public REST API (https://www.kaggle.com/api/v1/competitions/list),
authenticated with a Bearer token read from ~/.kaggle/access_token.
Normalizes data to the unified schema defined in section 7.

Field mapping notes (verified against live API payload 2026-08-28):
- title            -> title
- hostName         -> organizer (real host org, e.g. "OpenAI", "Abstraction and
                      Reasoning Corpus"); falls back to organizationName
- url              -> source_url
- description      -> description
- reward           -> prize_pool (parsed; e.g. "450,000 Usd", "Knowledge", "Swag")
- deadline         -> registration_deadline AND event_end_date
- teamCount        -> participant_count
- category         -> tags (plus tag names and evaluationMetric)
- enabledDate      -> NOT used as event_start_date (it is the date the competition
                      was enabled on the platform, not a participant start date)
- domains          -> default ["ai_ml"] (see justification below)
- mode             -> "online" (Kaggle competitions are inherently online)
- sponsors         -> [] (no sponsor field in payload)
- is_mlh_sanctioned -> False

Domains default justification:
Kaggle competitions are, by definition, machine-learning / data-science
competitions — the platform only hosts predictive-modeling and ML challenges.
Unlike Devpost/MLH/Topcoder (where a default domain would be a guess), every
Kaggle listing is inherently an AI/ML problem, so defaulting domains to
["ai_ml"] is accurate rather than a silent assumption.
"""
import os
import re
import json
import uuid
import requests
from datetime import datetime, timezone

API_URL = "https://www.kaggle.com/api/v1/competitions/list"
TOKEN_PATH = os.path.expanduser("~/.kaggle/access_token")
PAGE_SIZE = 20


def _read_token():
    """Read the Kaggle Bearer token from ~/.kaggle/access_token."""
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8-sig") as f:
            token = f.read().strip()
        return token or None
    except OSError:
        return None


def fetch_kaggle_competitions():
    """Fetch active Kaggle competitions from the public REST API."""
    token = _read_token()
    if not token:
        print("Kaggle: no access token found at ~/.kaggle/access_token")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    all_competitions = []
    page = 1
    try:
        while True:
            params = {"group": "general", "sortBy": "latestDeadline", "page": page}
            resp = requests.get(API_URL, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            all_competitions.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            page += 1
    except Exception as e:
        print(f"Error fetching from Kaggle: {e}")
    return all_competitions


def parse_prize(reward_str):
    """Parse Kaggle's reward field into the unified prize_pool structure.

    Examples of reward values: "450,000 Usd", "77,000 Usd", "Knowledge", "Swag".
    """
    if not reward_str:
        return {"amount": 0, "currency": "USD", "display_text": ""}

    clean = str(reward_str).strip()
    amount = 0
    currency = "USD"

    num_match = re.search(r"[\d,]+", clean)
    if num_match:
        try:
            amount = float(num_match.group().replace(",", ""))
        except ValueError:
            amount = 0

    # Currency is the trailing token (e.g. "Usd" -> "USD")
    parts = clean.split()
    if len(parts) >= 2:
        currency = parts[-1].upper()

    return {
        "amount": amount,
        "currency": currency,
        "display_text": clean,
    }


def normalize_kaggle(raw_competitions):
    """Normalize raw Kaggle competition dicts into the section-7 unified schema."""
    normalized = []
    now = datetime.now(timezone.utc).isoformat()

    for c in raw_competitions:
        # Organizer: hostName is the real host org; fall back to organizationName
        organizer = c.get("hostName") or c.get("organizationName") or "Kaggle"

        # Tags: category + tag names + evaluation metric
        tag_names = [t.get("name", "") for t in c.get("tags", []) if t.get("name")]
        category = c.get("category", "")
        metric = c.get("evaluationMetric", "")
        tags = list(filter(None, [category] + tag_names + [metric]))

        normalized_item = {
            "id": str(uuid.uuid4()),
            "title": c.get("title", ""),
            "organizer": organizer,
            "source_platform": "kaggle",
            "source_url": c.get("url", ""),
            "description": c.get("description", "") or "",
            # Kaggle competitions are inherently ML/data-science problems, so
            # defaulting to ["ai_ml"] is accurate (see module docstring).
            "domains": ["ai_ml"],
            "mode": "online",              # Kaggle competitions are inherently online
            "location": None,
            "prize_pool": parse_prize(c.get("reward", "")),
            "sponsors": [],                # no sponsor field in payload (verified)
            "registration_deadline": c.get("deadline"),
            "event_start_date": None,      # no real participant start date (verified)
            "event_end_date": c.get("deadline"),
            "participant_count": c.get("teamCount"),
            "impact_score": 0,
            "score_breakdown": {
                "organizer_tier": 0,
                "sponsor_recognition": 0,
                "prize_pool": 0,
                "domain_match": 0,
                "participation_scale": 0,
                "recency": 0,
            },
            "tags": tags,
            "is_mlh_sanctioned": False,
            "ingested_at": now,
            "last_updated_at": now,
        }
        normalized.append(normalized_item)

    return normalized


if __name__ == "__main__":
    print("Fetching Kaggle competitions...")
    raw = fetch_kaggle_competitions()
    print(f"Fetched {len(raw)} active competitions.")

    normalized = normalize_kaggle(raw)

    with open("kaggle_raw.json", "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)

    print("Saved to kaggle_raw.json")
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))