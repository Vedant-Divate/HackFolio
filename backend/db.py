"""
Database module for Hackfolio API
In-memory data store (will be replaced with MongoDB in Phase 3)
"""
import os
from typing import List, Optional

from pymongo import MongoClient

# In-memory data store
hackathons_db: List[dict] = []
alert_subscriptions_db: List[dict] = []
_mongo_client: Optional[MongoClient] = None
_hackathons_collection = None
_alerts_collection = None


def _connect_mongo() -> bool:
    global _mongo_client, _hackathons_collection, _alerts_collection
    if _hackathons_collection is not None:
        return True
    # Accept the existing .env spelling while keeping MONGODB_URI canonical.
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGODB_URL")
    if not uri:
        return False
    try:
        _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        _mongo_client.admin.command("ping")
        database = _mongo_client[os.getenv("MONGODB_DB_NAME", "hackfolio")]
        _hackathons_collection = database["hackathons"]
        _alerts_collection = database["alert_subscriptions"]
        return True
    except Exception as error:
        print(f"MongoDB unavailable; using in-memory storage: {error}")
        if _mongo_client is not None:
            _mongo_client.close()
        _mongo_client = None
        return False


def get_hackathons_db() -> List[dict]:
    """Return Mongo records or the in-memory fallback."""
    if _connect_mongo():
        try:
            return list(_hackathons_collection.find({}, {"_id": 0}))
        except Exception as error:
            print(f"MongoDB read failed; using in-memory storage: {error}")
    return hackathons_db


def upsert_hackathons(events: List[dict]) -> None:
    """Upsert by normalized stable id and retain the fallback copy."""
    global hackathons_db
    hackathons_db = list(events)
    if not _connect_mongo():
        return
    try:
        for event in events:
            _hackathons_collection.replace_one({"id": event["id"]}, event, upsert=True)
    except Exception as error:
        print(f"MongoDB upsert failed; in-memory copy retained: {error}")


def set_hackathons_db(events: List[dict]) -> None:
    """Backward-compatible startup helper."""
    upsert_hackathons(events)


def clear_hackathons_db() -> None:
    """Clear only memory; Mongo data survives application restarts."""
    global hackathons_db
    hackathons_db.clear()


def create_alert(subscription: dict) -> dict:
    alert_subscriptions_db.append(subscription)
    if _connect_mongo():
        try:
            _alerts_collection.replace_one({"id": subscription["id"]}, subscription, upsert=True)
        except Exception as error:
            print(f"MongoDB alert write failed; in-memory copy retained: {error}")
    return subscription


def get_alerts() -> List[dict]:
    if _connect_mongo():
        try:
            return list(_alerts_collection.find({}, {"_id": 0}))
        except Exception as error:
            print(f"MongoDB alert read failed; using in-memory storage: {error}")
    return alert_subscriptions_db


def delete_alert(alert_id: str) -> Optional[dict]:
    alerts = get_alerts()
    deleted = next((alert for alert in alerts if alert.get("id") == alert_id), None)
    if deleted is None:
        return None
    alert_subscriptions_db[:] = [alert for alert in alert_subscriptions_db if alert.get("id") != alert_id]
    if _connect_mongo():
        try:
            _alerts_collection.delete_one({"id": alert_id})
        except Exception as error:
            print(f"MongoDB alert delete failed; in-memory copy updated: {error}")
    return deleted