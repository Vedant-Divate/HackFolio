"""
Seed Companies Loader
Loads manual seed company hackathons from seed_companies.yaml
"""
import yaml
import os
from typing import List, Dict, Any


def load_seed_companies(filepath: str = "scrapers/seed_companies.yaml") -> List[Dict[str, Any]]:
    """Load seed companies from YAML file."""
    full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filepath)
    
    with open(full_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    if not data:
        return []
    
    # Ensure all entries have required fields
    for entry in data:
        entry.setdefault('source_platform', 'manual')
        entry.setdefault('category_tags', [])
        entry.setdefault('impact_score', 0)
        entry.setdefault('score_breakdown', {
            "organizer_tier": 0,
            "sponsor_recognition": 0,
            "prize_pool": 0,
            "participation_scale": 0,
            "recency": 0
        })
    
    return data


if __name__ == "__main__":
    companies = load_seed_companies()
    print(f"Loaded {len(companies)} seed companies")
    for c in companies:
        print(f"  - {c['title']} (tags: {c.get('category_tags', [])})")