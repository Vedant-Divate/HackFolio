"""
Database module for Hackfolio API
In-memory data store (will be replaced with MongoDB in Phase 3)
"""
from typing import List

# In-memory data store
hackathons_db: List[dict] = []


def get_hackathons_db() -> List[dict]:
    """Dependency to get the in-memory hackathons database."""
    return hackathons_db


def set_hackathons_db(events: List[dict]) -> None:
    """Set the hackathons database (used during startup)."""
    global hackathons_db
    hackathons_db = events


def clear_hackathons_db() -> None:
    """Clear the hackathons database (used during shutdown)."""
    global hackathons_db
    hackathons_db.clear()