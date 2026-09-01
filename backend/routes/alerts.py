"""
Alerts API Routes
POST /api/alerts/subscribe endpoint per section 9
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.db import get_hackathons_db

router = APIRouter()

# In-memory alert subscriptions store (will be replaced with MongoDB in Phase 3)
alert_subscriptions_db: List[dict] = []


class AlertSubscriptionRequest(BaseModel):
    """Request model for alert subscription."""
    hackathon_id: str = Field(..., description="ID of the hackathon to subscribe to")
    days_before: int = Field(3, ge=1, le=30, description="Days before deadline to send alert (1-30)")
    channel: str = Field("email", description="Notification channel: email, telegram, discord")


class AlertSubscriptionResponse(BaseModel):
    """Response model for alert subscription."""
    id: str
    hackathon_id: str
    days_before: int
    channel: str
    created_at: str


@router.post("/alerts/subscribe", response_model=AlertSubscriptionResponse)
async def subscribe_alert(
    request: AlertSubscriptionRequest,
    db: List[dict] = Depends(get_hackathons_db)
):
    """
    Subscribe to deadline alerts for a hackathon.
    
    Args:
        request: Alert subscription request with hackathon_id, days_before, and channel
        db: Hackathons database dependency
    
    Returns:
        Created alert subscription
    
    Raises:
        HTTPException: If hackathon not found or subscription already exists
    """
    # Verify hackathon exists
    hackathon = None
    for h in db:
        if h.get("id") == request.hackathon_id:
            hackathon = h
            break
    
    if not hackathon:
        raise HTTPException(status_code=404, detail="Hackathon not found")
    
    # Check if subscription already exists for this hackathon
    for sub in alert_subscriptions_db:
        if sub.get("hackathon_id") == request.hackathon_id:
            raise HTTPException(
                status_code=409, 
                detail="Alert subscription already exists for this hackathon"
            )
    
    # Create subscription
    subscription = {
        "id": f"alert_{len(alert_subscriptions_db) + 1}",
        "hackathon_id": request.hackathon_id,
        "days_before": request.days_before,
        "channel": request.channel,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    alert_subscriptions_db.append(subscription)
    
    return subscription


@router.get("/alerts")
async def list_alerts():
    """List all alert subscriptions."""
    return {
        "total": len(alert_subscriptions_db),
        "subscriptions": alert_subscriptions_db
    }


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    """Delete an alert subscription by ID."""
    global alert_subscriptions_db
    for i, sub in enumerate(alert_subscriptions_db):
        if sub.get("id") == alert_id:
            deleted = alert_subscriptions_db.pop(i)
            return {"message": "Alert subscription deleted", "deleted": deleted}
    raise HTTPException(status_code=404, detail="Alert subscription not found")