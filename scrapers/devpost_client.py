"""
Devpost Scraper Client
Implements section 11 (Phase 1) and section 4.1 for Devpost.
Normalizes data to the unified schema defined in section 7.
"""
import urllib.request
import json
import uuid
import ssl
from datetime import datetime, timezone
import re

def fetch_devpost_hackathons():
    """
    Fetch currently open/upcoming Devpost hackathons with pagination support.
    
    Uses status=open filter to only return active hackathons (not historical archive).
    Pagination terminates naturally based on API's total_count or empty response.
    """
    base_url = "https://devpost.com/api/hackathons"
    # Bypass SSL verification for local dev environments that might have issues
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    all_hackathons = []
    page = 1
    seen_titles = set()
    
    while True:
        # Use status=open filter to get only currently active hackathons
        url = f"{base_url}?status=open&page={page}"
        req = urllib.request.Request(url)
        
        try:
            response = urllib.request.urlopen(req, context=ctx)
            data = json.loads(response.read())
            
            hackathons = data.get('hackathons', [])
            if not hackathons:
                print(f"  Page {page} returned empty results, stopping")
                break
            
            # Check for duplicate content (API sometimes returns same page)
            page_titles = [h.get('title', '') for h in hackathons]
            if all(t in seen_titles for t in page_titles):
                print(f"  Page {page} contains only duplicate titles, stopping")
                break
            
            # Add new titles to seen set
            for t in page_titles:
                seen_titles.add(t)
                
            all_hackathons.extend(hackathons)
            print(f"  Fetched page {page}: {len(hackathons)} hackathons (total: {len(all_hackathons)})")
            
            # Check if we've fetched all available pages per API meta
            meta = data.get('meta', {})
            total_count = meta.get('total_count', 0)
            per_page = meta.get('per_page', 9)
            
            if total_count and len(all_hackathons) >= total_count:
                print(f"  Reached API reported total_count ({total_count})")
                break
                
            page += 1
            
            # Small delay to be respectful to the API
            import time
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Error fetching page {page} from Devpost: {e}")
            break
    
    return all_hackathons

def map_domain(theme_name):
    # Mapping Devpost themes to unified domains: ai_ml, blockchain, full_stack, security, web3, cloud
    name = theme_name.lower()
    if 'machine learning' in name or 'ai' in name:
        return 'ai_ml'
    if 'blockchain' in name or 'crypto' in name or 'web3' in name:
        return 'blockchain'
    if 'security' in name:
        return 'security'
    if 'cloud' in name:
        return 'cloud'
    return None

def parse_devpost_dates(date_str):
    if not date_str:
        return None, None
    try:
        if ',' in date_str:
            period, year = date_str.split(',')
            year = year.strip()
            if '-' in period:
                start_str, end_str = period.split('-')
                start_str = start_str.strip()
                end_str = end_str.strip()
                if ' ' not in end_str:
                    end_str = start_str.split(' ')[0] + ' ' + end_str
                
                start_dt = datetime.strptime(f'{start_str} {year}', '%b %d %Y')
                end_dt = datetime.strptime(f'{end_str} {year}', '%b %d %Y')
                return start_dt.isoformat() + 'Z', end_dt.isoformat() + 'Z'
    except Exception as e:
        pass
    return None, None

def parse_prize(prize_str):
    if not prize_str:
        return {"amount": 0, "currency": "USD", "display_text": "0"}
    
    # Example: "$<span data-currency-value>740,000</span>"
    clean_str = re.sub(r'<[^>]+>', '', str(prize_str)).strip()
    
    amount = 0
    currency = "USD"
    if clean_str.startswith('$'):
        currency = "USD"
    elif clean_str.startswith('₹'):
        currency = "INR"
    elif clean_str.startswith('€'):
        currency = "EUR"
    
    num_match = re.search(r'[\d,]+', clean_str)
    if num_match:
        try:
            amount = float(num_match.group().replace(',', ''))
        except:
            pass
            
    return {
        "amount": amount,
        "currency": currency,
        "display_text": clean_str
    }

def normalize_devpost(raw_hackathons):
    normalized = []
    now = datetime.now(timezone.utc).isoformat()
    
    for h in raw_hackathons:
        loc = h.get('displayed_location', {}).get('location', '')
        mode = 'online'
        if 'online' not in loc.lower() and loc:
            mode = 'offline'
            
        prize_pool = parse_prize(h.get('prize_amount', ''))
        
        mapped_domains = [map_domain(t.get('name', '')) for t in h.get('themes', [])]
        domains = list(set([d for d in mapped_domains if d is not None]))
        
        start_date, end_date = parse_devpost_dates(h.get('submission_period_dates', ''))
        
        org_name = h.get('organization_name')
        if org_name:
            org_name = org_name.strip()
        else:
            org_name = ''
        organizer = org_name if org_name else 'Devpost (Unknown)'
        sponsors = [org_name] if org_name else []
        
        normalized_item = {
            "id": str(uuid.uuid4()),
            "title": h.get('title', ''),
            "organizer": organizer,
            "source_platform": "devpost",
            "source_url": h.get('url', ''),
            "description": "",
            "domains": domains,
            "mode": mode,
            "location": loc if mode != 'online' else None,
            "prize_pool": prize_pool,
            "sponsors": sponsors,
            "registration_deadline": end_date,
            "event_start_date": start_date,
            "event_end_date": end_date,
            "participant_count": h.get('registrations_count', 0),
            "impact_score": 0,
            "score_breakdown": {
                "organizer_tier": 0,
                "sponsor_recognition": 0,
                "prize_pool": 0,
                "domain_match": 0,
                "participation_scale": 0,
                "recency": 0
            },
            "tags": [t.get('name', '') for t in h.get('themes', [])],
            "is_mlh_sanctioned": False,
            "ingested_at": now,
            "last_updated_at": now
        }
        normalized.append(normalized_item)
        
    return normalized

if __name__ == "__main__":
    print("Fetching Devpost hackathons...")
    raw = fetch_devpost_hackathons()
    print(f"Fetched {len(raw)} items.")
    
    normalized = normalize_devpost(raw)
    
    with open('devpost_raw.json', 'w', encoding='utf-8') as f:
        json.dump(normalized, f, indent=2)
        
    print("Saved to devpost_raw.json")
    if normalized:
        print("Sample output:")
        print(json.dumps(normalized[0], indent=2))
