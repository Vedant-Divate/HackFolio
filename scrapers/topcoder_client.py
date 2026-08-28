"""
Topcoder Scraper Client
Implements section 11 (Phase 1) and section 4.1 for Topcoder.
Access method: Public REST API v6 (https://api.topcoder.com/v6/challenges).
Normalizes data to the unified schema defined in section 7.

Field mapping notes (verified against live v6 API payload 2026-08-28):
- name          -> title
- description   -> description (markdown text, present in v6)
- track.name    -> tags (e.g. "Quality Assurance", "Development")
- skills        -> tags (skill names appended)
- type.name     -> tags (e.g. "Challenge", "Task")
- registrationEndDate -> registration_deadline (explicit separate field, present)
- startDate     -> event_start_date
- endDate       -> event_end_date
- numOfRegistrants -> participant_count
- prizeSets[PLACEMENT].prizes[*].value -> prize_pool.amount (summed)
- overview.totalPrizes / overview.type -> prize_pool.display_text
- organizer: not in payload — Topcoder is both the platform and the organizer; defaults to "Topcoder"
- sponsors: not in payload — left as empty array
- mode: Topcoder challenges are inherently online — hardcoded "online"
- is_mlh_sanctioned: False
"""
import urllib.request
import ssl
import json
import uuid
from datetime import datetime, timezone

API_URL = "https://api.topcoder.com/v6/challenges"
PER_PAGE = 50


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_topcoder_challenges():
    """Fetch active Topcoder challenges from the public v6 API."""
    all_challenges = []
    page = 1
    try:
        while True:
            url = f"{API_URL}?status=Active&perPage={PER_PAGE}&page={page}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            )
            resp = urllib.request.urlopen(req, context=_ssl_ctx(), timeout=15)
            batch = json.loads(resp.read().decode("utf-8"))
            if not batch:
                break
            all_challenges.extend(batch)
            if len(batch) < PER_PAGE:
                break
            page += 1
    except Exception as e:
        print(f"Error fetching from Topcoder: {e}")
    return all_challenges


def _map_domain(track_name, skill_names):
    """Map Topcoder track + skills to unified domain taxonomy."""
    combined = (track_name + " " + " ".join(skill_names)).lower()
    domains = set()
    if any(k in combined for k in ["machine learning", "ai", "data science", "deep learning", "nlp"]):
        domains.add("ai_ml")
    if any(k in combined for k in ["blockchain", "crypto", "web3", "ethereum", "solidity", "defi"]):
        domains.add("blockchain")
    if any(k in combined for k in ["security", "cybersecurity", "penetration", "vulnerability", "forensics"]):
        domains.add("security")
    if any(k in combined for k in ["cloud", "aws", "azure", "gcp", "kubernetes", "devops"]):
        domains.add("cloud")
    if any(k in combined for k in ["web3", "nft", "defi", "smart contract"]):
        domains.add("web3")
    # full_stack only if explicit and nothing else matched
    if any(k in combined for k in ["full stack", "frontend", "backend", "web development", "react", "node"]):
        domains.add("full_stack")
    return list(domains)


def _sum_prizes(prize_sets):
    """Sum all PLACEMENT prizes across prizeSets."""
    total = 0
    currency = "USD"
    for ps in prize_sets or []:
        if ps.get("type") == "PLACEMENT":
            for prize in ps.get("prizes", []):
                total += prize.get("value", 0)
                currency = prize.get("type", "USD")
    return total, currency


def normalize_topcoder(raw_challenges):
    """Normalize raw Topcoder challenge dicts into the section-7 unified schema."""
    normalized = []
    now = datetime.now(timezone.utc).isoformat()

    for h in raw_challenges:
        # Skills
        skill_names = [s.get("name", "") for s in h.get("skills", [])]
        track_name = (h.get("track") or {}).get("name", "")
        type_name = (h.get("type") or {}).get("name", "")

        domains = _map_domain(track_name, skill_names)

        prize_amount, currency = _sum_prizes(h.get("prizeSets", []))
        overview = h.get("overview") or {}
        display_text = f"{overview.get('totalPrizes', prize_amount)} {overview.get('type', currency)}" if overview else f"{prize_amount} {currency}"

        tags = list(filter(None, [track_name, type_name] + skill_names))

        # source_url: canonical Topcoder challenge URL
        challenge_id = h.get("id", "")
        source_url = f"https://www.topcoder.com/challenges/{challenge_id}" if challenge_id else ""

        normalized_item = {
            "id": str(uuid.uuid4()),
            "title": h.get("name", ""),
            "organizer": "Topcoder",       # no per-challenge organizer field in payload (verified)
            "source_platform": "topcoder",
            "source_url": source_url,
            "description": h.get("description", "") or "",
            "domains": domains,
            "mode": "online",              # Topcoder challenges are inherently online (verified)
            "location": None,
            "prize_pool": {
                "amount": prize_amount,
                "currency": currency,
                "display_text": display_text,
            },
            "sponsors": [],                # no sponsor field in payload (verified)
            "registration_deadline": h.get("registrationEndDate"),   # explicit ISO8601 field (verified)
            "event_start_date": h.get("startDate"),
            "event_end_date": h.get("endDate"),
            "participant_count": h.get("numOfRegistrants"),
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
    print("Fetching Topcoder challenges...")
    raw = fetch_topcoder_challenges()
    print(f"Fetched {len(raw)} active challenges.")

    normalized = normalize_topcoder(raw)

    with open("topcoder_raw.json", "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)

    print("Saved to topcoder_raw.json")
    if normalized:
        print("\nSample normalized output:")
        print(json.dumps(normalized[0], indent=2))
