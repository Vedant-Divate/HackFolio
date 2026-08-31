"""
Hackfolio Deduplication Engine
Implements section 5.3 fuzzy-match deduplication on (event name + date window + organizer)
using rapidfuzz. Keeps the entry with the most complete metadata when two sources list
the same event.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rapidfuzz import fuzz, process
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
import copy


class HackathonDeduplicator:
    def __init__(
        self,
        name_threshold: int = 85,
        date_window_days: int = 7,
        organizer_threshold: int = 80
    ):
        """
        Initialize deduplicator with similarity thresholds.
        
        Args:
            name_threshold: Minimum name similarity (0-100) to consider a match
            date_window_days: Maximum days between event dates to consider same event
            organizer_threshold: Minimum organizer similarity (0-100) to consider a match
        """
        self.name_threshold = name_threshold
        self.date_window_days = date_window_days
        self.organizer_threshold = organizer_threshold
    
    def _normalize_name(self, name: str) -> str:
        """Normalize event name for comparison."""
        if not name:
            return ""
        # Lowercase, remove special chars, extra spaces
        normalized = name.lower().strip()
        # Remove common suffixes/prefixes that vary by platform
        normalized = normalized.replace("hackathon", "").replace("challenge", "").replace("competition", "")
        normalized = normalized.replace("2024", "").replace("2025", "").replace("2026", "")
        normalized = " ".join(normalized.split())
        return normalized
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO8601 date string to datetime."""
        if not date_str:
            return None
        try:
            if date_str.endswith('Z'):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return datetime.fromisoformat(date_str)
        except Exception:
            return None
    
    def _dates_within_window(self, date1: Optional[str], date2: Optional[str]) -> bool:
        """Check if two dates are within the configured window."""
        dt1 = self._parse_date(date1)
        dt2 = self._parse_date(date2)
        
        if not dt1 or not dt2:
            return False  # Can't verify date proximity
        
        # Make both timezone-aware
        if dt1.tzinfo is None:
            dt1 = dt1.replace(tzinfo=timezone.utc)
        if dt2.tzinfo is None:
            dt2 = dt2.replace(tzinfo=timezone.utc)
        
        diff_days = abs((dt1 - dt2).total_seconds()) / 86400
        return diff_days <= self.date_window_days
    
    def _organizer_similarity(self, org1: str, org2: str) -> int:
        """Compute organizer similarity score (0-100)."""
        if not org1 or not org2:
            return 0
        return fuzz.ratio(org1.lower().strip(), org2.lower().strip())
    
    def _metadata_completeness(self, event: Dict[str, Any]) -> int:
        """
        Score metadata completeness (higher = more complete).
        Used to decide which duplicate to keep.
        """
        score = 0
        # Required fields
        if event.get('title'): score += 10
        if event.get('organizer'): score += 10
        if event.get('source_url'): score += 10
        if event.get('description'): score += 15
        if event.get('domains'): score += 10
        if event.get('mode'): score += 5
        if event.get('location'): score += 5
        if event.get('prize_pool', {}).get('amount', 0) > 0: score += 15
        if event.get('prize_pool', {}).get('display_text'): score += 5
        if event.get('sponsors'): score += 10
        if event.get('registration_deadline'): score += 5
        if event.get('event_start_date'): score += 5
        if event.get('event_end_date'): score += 5
        if event.get('participant_count'): score += 5
        if event.get('tags'): score += 5
        return score
    
    def _events_match(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> bool:
        """Check if two events are likely the same hackathon."""
        # SAME SOURCE: require exact source_url match (same platform shouldn't have
        # fuzzy duplicates - different tracks have different URLs)
        source1 = event1.get('source_platform', '')
        source2 = event2.get('source_platform', '')
        
        if source1 and source1 == source2:
            # Same source platform - only duplicate if exact same URL
            url1 = event1.get('source_url', '')
            url2 = event2.get('source_url', '')
            return url1 and url2 and url1 == url2
        
        # CROSS SOURCE: use fuzzy matching on name + date window + organizer
        # Name similarity
        name1 = self._normalize_name(event1.get('title', ''))
        name2 = self._normalize_name(event2.get('title', ''))
        name_score = fuzz.ratio(name1, name2)
        
        if name_score < self.name_threshold:
            return False
        
        # Date proximity (use registration_deadline or event_end_date)
        date1 = event1.get('registration_deadline') or event1.get('event_end_date')
        date2 = event2.get('registration_deadline') or event2.get('event_end_date')
        if not self._dates_within_window(date1, date2):
            return False
        
        # Organizer similarity
        org_score = self._organizer_similarity(
            event1.get('organizer', ''),
            event2.get('organizer', '')
        )
        if org_score < self.organizer_threshold:
            return False
        
        return True
    
    def deduplicate(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate a list of events.
        Returns a list with duplicates removed, keeping the most complete entry.
        """
        if not events:
            return []
        
        # Group by source_platform to avoid self-deduping within same source
        # (same source shouldn't have duplicates, but cross-source will)
        unique_events = []
        seen_indices = set()
        
        for i, event1 in enumerate(events):
            if i in seen_indices:
                continue
            
            # Find all duplicates of this event
            duplicate_group = [event1]
            duplicate_indices = {i}
            
            for j, event2 in enumerate(events[i+1:], start=i+1):
                if j in seen_indices:
                    continue
                if self._events_match(event1, event2):
                    duplicate_group.append(event2)
                    duplicate_indices.add(j)
            
            # Keep the most complete entry
            best_event = max(duplicate_group, key=self._metadata_completeness)
            
            # Merge useful fields from duplicates into best event
            merged_event = self._merge_duplicates(best_event, duplicate_group)
            unique_events.append(merged_event)
            seen_indices.update(duplicate_indices)
        
        return unique_events
    
    def _merge_duplicates(self, primary: Dict[str, Any], duplicates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge useful metadata from duplicates into the primary event.
        Primary is the most complete event; we enrich it with non-empty fields from others.
        """
        merged = copy.deepcopy(primary)
        
        # Fields to merge (take non-empty from duplicates if primary is empty)
        merge_fields = [
            'description', 'domains', 'location', 'prize_pool', 'sponsors',
            'registration_deadline', 'event_start_date', 'event_end_date',
            'participant_count', 'tags', 'source_url'
        ]
        
        for dup in duplicates:
            if dup is primary:
                continue
            for field in merge_fields:
                primary_val = merged.get(field)
                dup_val = dup.get(field)
                
                # Check if primary is empty/missing and duplicate has value
                if self._is_empty(primary_val) and not self._is_empty(dup_val):
                    merged[field] = copy.deepcopy(dup_val)
        
        # Track all source platforms this event came from
        sources = set(e.get('source_platform') for e in duplicates)
        merged['source_platforms'] = list(sources)
        merged['deduplicated_from'] = len(duplicates)
        
        return merged
    
    def _is_empty(self, value: Any) -> bool:
        """Check if a value is empty/missing."""
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, (list, dict)) and not value:
            return True
        if isinstance(value, (int, float)) and value == 0:
            return True
        return False


def deduplicate_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convenience function to deduplicate events with default thresholds."""
    deduplicator = HackathonDeduplicator()
    return deduplicator.deduplicate(events)


if __name__ == "__main__":
    # Test with sample data
    import json
    from scrapers.devpost_client import fetch_devpost_hackathons, normalize_devpost
    from scrapers.mlh_client import fetch_mlh_events, normalize_mlh
    from scrapers.topcoder_client import fetch_topcoder_challenges, normalize_topcoder
    from scrapers.kaggle_client import fetch_kaggle_competitions, normalize_kaggle
    
    print("Fetching real data from all 4 Phase 1 sources...")
    
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
    print(f"\nTotal before dedupe: {len(all_events)}")
    
    # Deduplicate
    deduplicator = HackathonDeduplicator()
    deduped = deduplicator.deduplicate(all_events)
    print(f"Total after dedupe: {len(deduped)}")
    print(f"Removed {len(all_events) - len(deduped)} duplicates")
    
    # Show any events that were deduplicated
    print("\nDeduplicated events (merged from multiple sources):")
    for event in deduped:
        if event.get('deduplicated_from', 1) > 1:
            print(f"  - {event['title']} (from {event['source_platforms']})")