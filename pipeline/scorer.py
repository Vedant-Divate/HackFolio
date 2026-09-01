"""
Hackfolio Impact Scoring Engine
Implements the Impact Score algorithm per section 5 of the spec.

Weights are loaded from scoring_config.yaml (not hardcoded).
Handles two critical data-quality issues:
1. prize_pool.amount: 0 does NOT always mean "no prize" - check display_text/source_platform
2. participant_count scale varies by source/category - normalize per-source
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import math
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict
import statistics


# MVP stopgap rates; replace with a dated FX service or configured rates later.
FIXED_USD_RATES = {
    'USD': 1.0,
    'JPY': 0.0067,
    'EUR': 1.08,
    'GBP': 1.27,
    'INR': 0.012,
}


class ImpactScorer:
    def __init__(self, config_path: str = "pipeline/scoring_config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.weights = self.config['weights']
        # Verify weights sum to 1.0
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            raise ValueError(f"Weights sum to {weight_sum}, expected 1.0")
        
        # Pre-load recognized brands for sponsor scoring
        self.recognized_brands = set(b.lower() for b in self.config['sponsor_recognition']['recognized_brands'])
        self.high_tier_organizers = set(o.lower() for o in self.config['organizer_tier']['high_tier_organizers'])
        
        # Per-source participation stats (computed at runtime)
        self._participation_stats: Dict[str, Dict[str, float]] = {}
    
    def compute_participation_stats(self, events: List[Dict[str, Any]]) -> None:
        """
        Compute per-source participation percentiles for normalization.
        This handles the data-quality issue where participant_count scale varies wildly by source.
        """
        source_participants = defaultdict(list)
        
        for event in events:
            source = event.get('source_platform', 'unknown')
            count = event.get('participant_count')
            if count is not None and count > 0:
                source_participants[source].append(count)
        
        for source, counts in source_participants.items():
            if len(counts) >= 2:
                sorted_counts = sorted(counts)
                low_idx = int(len(sorted_counts) * self.config['participation_scale']['low_percentile'])
                high_idx = int(len(sorted_counts) * self.config['participation_scale']['high_percentile'])
                self._participation_stats[source] = {
                    'low': sorted_counts[low_idx],
                    'high': sorted_counts[high_idx],
                    'median': statistics.median(sorted_counts),
                    'max': max(sorted_counts)
                }
            elif len(counts) == 1:
                self._participation_stats[source] = {
                    'low': counts[0],
                    'high': counts[0],
                    'median': counts[0],
                    'max': counts[0]
                }
    
    def score_organizer_tier(self, event: Dict[str, Any]) -> float:
        """Score organizer tier (0-1). MLH-sanctioned and known high-tier orgs get high scores."""
        organizer = (event.get('organizer') or '').lower()
        is_mlh = event.get('is_mlh_sanctioned', False)
        
        if is_mlh or any(high in organizer for high in self.high_tier_organizers):
            return self.config['organizer_tier']['high_tier_score']
        
        # Check if organizer is a known company (has some recognition)
        if organizer and organizer not in ['devpost (unknown)', 'unknown', '']:
            return self.config['organizer_tier']['medium_tier_score']
        
        return self.config['organizer_tier']['low_tier_score']
    
    def score_sponsor_recognition(self, event: Dict[str, Any]) -> float:
        """Score sponsor recognition (0-1) based on recognized brands in sponsors list."""
        sponsors = event.get('sponsors', [])
        if not sponsors:
            return 0.0
        
        recognized_count = 0
        for sponsor in sponsors:
            sponsor_lower = sponsor.lower()
            if any(brand in sponsor_lower for brand in self.recognized_brands):
                recognized_count += 1
        
        max_sponsors = self.config['sponsor_recognition']['max_sponsors_for_full_score']
        per_sponsor = self.config['sponsor_recognition']['per_sponsor_score']
        
        score = min(recognized_count * per_sponsor, 1.0)
        return score
    
    def score_prize_pool(self, event: Dict[str, Any]) -> float:
        """
        Score prize pool (0-1) with special handling for data-quality issues:
        - amount=0 with display_text like "Knowledge", "Swag" (Kaggle) = non-monetary, small base score
        - amount=0 with empty display_text (MLH) = no data, don't penalize, treat as unknown
        - Normalize monetary amounts against floor/ceiling
        """
        prize_pool = event.get('prize_pool') or {}
        amount = prize_pool.get('amount', 0)
        display_text = (prize_pool.get('display_text') or '').strip().lower()
        source = event.get('source_platform', '')
        
        # Case 1: Non-monetary rewards (Kaggle "Knowledge", "Swag", etc.)
        non_monetary_keywords = ['knowledge', 'swag', 'merch', 'credits', 'badge', 'certificate', 'internship', 'job', 'mentorship']
        if amount == 0 and any(kw in display_text for kw in non_monetary_keywords):
            return self.config['prize_pool']['non_monetary_base_score']
        
        # Case 2: No prize data available (MLH, some Devpost) - don't penalize, return neutral
        if amount == 0 and (not display_text or display_text in ['0', '']):
            # Return a neutral score (middle) rather than penalizing
            return 0.3
        
        # Case 3: Monetary prize - normalize against floor/ceiling
        floor = self.config['prize_pool']['floor_usd']
        ceiling = self.config['prize_pool']['ceiling_usd']
        
        currency = str(prize_pool.get('currency', 'USD')).upper()
        usd_rate = FIXED_USD_RATES.get(currency)
        if usd_rate is None:
            # Confirmed monetary value, but its scale cannot be compared safely.
            return 0.3
        amount_usd = amount * usd_rate
        
        if amount_usd <= floor:
            return 0.1
        elif amount_usd >= ceiling:
            return 1.0
        else:
            # Logarithmic scaling between floor and ceiling
            log_floor = math.log(floor)
            log_ceiling = math.log(ceiling)
            log_amount = math.log(amount_usd)
            return (log_amount - log_floor) / (log_ceiling - log_floor)
    
    def score_participation_scale(self, event: Dict[str, Any]) -> float:
        """
        Score participation scale (0-1) normalized per-source.
        Handles the data-quality issue where scale varies by source/category.
        """
        count = event.get('participant_count')
        source = event.get('source_platform', 'unknown')
        
        if count is None or count <= 0:
            return 0.1
        
        stats = self._participation_stats.get(source)
        if not stats:
            # No stats for this source - use raw count with diminishing returns
            return min(math.log(count + 1) / math.log(10000), 1.0)
        
        low = stats['low']
        high = stats['high']
        low_score = self.config['participation_scale']['low_score']
        high_score = self.config['participation_scale']['high_score']
        
        if count <= low:
            return low_score
        elif count >= high:
            return high_score
        else:
            # Linear interpolation between low and high percentiles
            ratio = (count - low) / (high - low) if high > low else 0.5
            return low_score + ratio * (high_score - low_score)
    
    def score_recency(self, event: Dict[str, Any]) -> float:
        """Score recency/activity (0-1) based on registration deadline."""
        deadline_str = event.get('registration_deadline') or event.get('event_end_date')
        if not deadline_str:
            return 0.5  # Unknown deadline = neutral
        
        try:
            # Parse ISO8601 datetime
            if deadline_str.endswith('Z'):
                deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
            else:
                deadline = datetime.fromisoformat(deadline_str)
            
            now = datetime.now(timezone.utc)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            
            days_until = (deadline - now).total_seconds() / 86400
            
            active_window = self.config['recency']['active_window_days']
            expired_penalty = self.config['recency']['expired_penalty_days']
            max_score = self.config['recency']['max_score']
            min_score = self.config['recency']['min_score']
            
            if days_until > active_window:
                return max_score
            elif days_until > 0:
                # Linear decay from max to min over active_window
                return max_score - (max_score - min_score) * (1 - days_until / active_window)
            elif days_until > -expired_penalty:
                # Recently expired - small penalty
                return min_score + (max_score - min_score) * 0.3
            else:
                # Long expired
                return min_score
                
        except Exception:
            return 0.5  # Parse error = neutral
    
    def score_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Compute full impact score for a single event."""
        # Compute individual factor scores (0-1 each)
        organizer_tier = self.score_organizer_tier(event)
        sponsor_recognition = self.score_sponsor_recognition(event)
        prize_pool = self.score_prize_pool(event)
        participation_scale = self.score_participation_scale(event)
        recency = self.score_recency(event)
        
        # Weighted sum (weights sum to 1.0)
        impact_score = (
            organizer_tier * self.weights['organizer_tier'] +
            sponsor_recognition * self.weights['sponsor_recognition'] +
            prize_pool * self.weights['prize_pool'] +
            participation_scale * self.weights['participation_scale'] +
            recency * self.weights['recency']
        ) * 100  # Convert to 0-100 scale
        
        # Round to 1 decimal
        impact_score = round(impact_score, 1)
        
        # Determine tier
        if impact_score >= self.config['score_tiers']['top_tier']:
            tier = "Top Tier"
        elif impact_score >= self.config['score_tiers']['solid']:
            tier = "Solid"
        else:
            tier = "Low Priority"
        
        return {
            "impact_score": impact_score,
            "score_breakdown": {
                "organizer_tier": round(organizer_tier * 100, 1),
                "sponsor_recognition": round(sponsor_recognition * 100, 1),
                "prize_pool": round(prize_pool * 100, 1),
                "participation_scale": round(participation_scale * 100, 1),
                "recency": round(recency * 100, 1)
            },
            "score_tier": tier
        }
    
    def score_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score a list of events, computing per-source participation stats first."""
        # First pass: compute participation stats per source
        self.compute_participation_stats(events)
        
        # Second pass: score each event
        scored_events = []
        for event in events:
            score_result = self.score_event(event)
            # Create a copy with score fields added
            scored_event = event.copy()
            scored_event.update(score_result)
            scored_events.append(scored_event)
        
        # Sort by impact_score descending
        scored_events.sort(key=lambda e: e['impact_score'], reverse=True)
        return scored_events


def main():
    """Test scorer with real data from Phase 1 clients."""
    import json
    from scrapers.devpost_client import fetch_devpost_hackathons, normalize_devpost
    from scrapers.mlh_client import fetch_mlh_events, normalize_mlh
    from scrapers.topcoder_client import fetch_topcoder_challenges, normalize_topcoder
    from scrapers.kaggle_client import fetch_kaggle_competitions, normalize_kaggle
    
    print("Fetching real data from all 4 Phase 1 sources...")
    
    # Fetch and normalize all sources
    devpost_raw = fetch_devpost_hackathons()
    devpost_events = normalize_devpost(devpost_raw)
    print(f"Devpost: {len(devpost_events)} events")
    
    mlh_raw = fetch_mlh_events()
    mlh_events = normalize_mlh(mlh_raw)
    print(f"MLH: {len(mlh_events)} events")
    
    topcoder_raw = fetch_topcoder_challenges()
    topcoder_events = normalize_topcoder(topcoder_raw)
    print(f"Topcoder: {len(topcoder_events)} events")
    
    kaggle_raw = fetch_kaggle_competitions()
    kaggle_events = normalize_kaggle(kaggle_raw)
    print(f"Kaggle: {len(kaggle_events)} events")
    
    all_events = devpost_events + mlh_events + topcoder_events + kaggle_events
    print(f"\nTotal events: {len(all_events)}")
    
    # Score all events
    scorer = ImpactScorer()
    scored_events = scorer.score_events(all_events)
    
    # Print top 20
    print("\n" + "="*100)
    print("TOP 20 HACKATHONS BY IMPACT SCORE")
    print("="*100)
    print(f"{'Rank':<4} {'Score':<6} {'Tier':<12} {'Source':<12} {'Title':<50} {'Organizer':<20}")
    print("-"*100)
    
    for i, event in enumerate(scored_events[:20], 1):
        title = event['title'][:48]
        organizer = event['organizer'][:18]
        source = event['source_platform']
        score = event['impact_score']
        tier = event['score_tier']
        print(f"{i:<4} {score:<6} {tier:<12} {source:<12} {title:<50} {organizer:<20}")
    
    # Print detailed breakdown for top 5
    print("\n" + "="*100)
    print("DETAILED SCORE BREAKDOWN - TOP 5")
    print("="*100)
    
    for i, event in enumerate(scored_events[:5], 1):
        print(f"\n#{i}: {event['title']}")
        print(f"  Source: {event['source_platform']} | Organizer: {event['organizer']}")
        print(f"  Prize: {event['prize_pool'].get('display_text', 'N/A')} | Participants: {event.get('participant_count', 'N/A')}")
        print(f"  Deadline: {event.get('registration_deadline', 'N/A')}")
        print(f"  Impact Score: {event['impact_score']} ({event['score_tier']})")
        print(f"  Breakdown:")
        for factor, score in event['score_breakdown'].items():
            weight = scorer.weights.get(factor, 0) * 100
            print(f"    {factor}: {score}/100 (weight: {weight:.1f}%)")
    
    # Show some Kaggle non-monetary examples
    print("\n" + "="*100)
    print("KAGGLE NON-MONETARY PRIZE EXAMPLES (amount=0, display_text='Knowledge'/'Swag')")
    print("="*100)
    kaggle_scored = [e for e in scored_events if e['source_platform'] == 'kaggle']
    for event in kaggle_scored[:5]:
        prize = event['prize_pool']
        print(f"  {event['title'][:60]}")
        print(f"    amount={prize['amount']}, display_text='{prize['display_text']}', prize_score={event['score_breakdown']['prize_pool']}")
    
    # Show MLH zero-prize examples
    print("\n" + "="*100)
    print("MLH ZERO-PRIZE EXAMPLES (amount=0, display_text='')")
    print("="*100)
    mlh_scored = [e for e in scored_events if e['source_platform'] == 'mlh']
    for event in mlh_scored[:5]:
        prize = event['prize_pool']
        print(f"  {event['title'][:60]}")
        print(f"    amount={prize['amount']}, display_text='{prize['display_text']}', prize_score={event['score_breakdown']['prize_pool']}")


if __name__ == "__main__":
    main()