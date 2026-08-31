"""
Hackathons API Routes
GET /api/hackathons endpoint with filtering per section 9
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.db import get_hackathons_db

router = APIRouter()


@router.get("/hackathons")
async def get_hackathons(
    db: List[dict] = Depends(get_hackathons_db),
    domain: Optional[str] = Query(None, description="Comma-separated domains: ai_ml,blockchain,full_stack,security,web3,cloud"),
    min_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum impact score (0-100)"),
    mode: Optional[str] = Query(None, description="Mode: online, offline, hybrid"),
    deadline_before: Optional[str] = Query(None, description="ISO8601 deadline filter (registration_deadline <= this date)"),
    sort: Optional[str] = Query("score_desc", description="Sort: score_desc, deadline_asc, prize_desc"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Get filtered and sorted hackathons.
    
    Filter params (per section 9):
    - domain: comma-separated domains (ai_ml, blockchain, full_stack, security, web3, cloud)
    - min_score: minimum impact score (0-100)
    - mode: online | offline | hybrid
    - deadline_before: ISO8601 date, filter events with registration_deadline <= this date
    - sort: score_desc | deadline_asc | prize_desc
    """
    results = db
    
    # Filter by domain
    if domain:
        domain_list = [d.strip() for d in domain.split(",")]
        results = [
            h for h in results
            if any(d in h.get("domains", []) for d in domain_list)
        ]
    
    # Filter by minimum score
    if min_score is not None:
        results = [h for h in results if h.get("impact_score", 0) >= min_score]
    
    # Filter by mode
    if mode:
        results = [h for h in results if h.get("mode", "").lower() == mode.lower()]
    
    # Filter by deadline
    if deadline_before:
        try:
            deadline_dt = datetime.fromisoformat(deadline_before.replace('Z', '+00:00'))
            filtered = []
            for h in results:
                reg_deadline = h.get("registration_deadline")
                if reg_deadline:
                    try:
                        reg_dt = datetime.fromisoformat(reg_deadline.replace('Z', '+00:00'))
                        if reg_dt <= deadline_dt:
                            filtered.append(h)
                    except Exception:
                        pass  # Skip events with unparseable deadlines
            results = filtered
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid deadline_before format. Use ISO8601.")
    
    # Sort
    if sort == "score_desc":
        results.sort(key=lambda h: h.get("impact_score", 0), reverse=True)
    elif sort == "deadline_asc":
        def get_deadline(h):
            reg = h.get("registration_deadline")
            if reg:
                try:
                    return datetime.fromisoformat(reg.replace('Z', '+00:00'))
                except Exception:
                    pass
            return datetime.max
        results.sort(key=get_deadline)
    elif sort == "prize_desc":
        results.sort(key=lambda h: h.get("prize_pool", {}).get("amount", 0), reverse=True)
    else:
        # Default: score_desc
        results.sort(key=lambda h: h.get("impact_score", 0), reverse=True)
    
    # Pagination
    total = len(results)
    results = results[offset:offset + limit]
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results
    }


@router.get("/hackathons/{hackathon_id}")
async def get_hackathon(
    hackathon_id: str,
    db: List[dict] = Depends(get_hackathons_db)
):
    """Get a single hackathon by ID."""
    for h in db:
        if h.get("id") == hackathon_id:
            return h
    raise HTTPException(status_code=404, detail="Hackathon not found")


@router.get("/stats")
async def get_stats(db: List[dict] = Depends(get_hackathons_db)):
    """Get aggregate statistics about the hackathon database."""
    if not db:
        return {"total": 0, "by_source": {}, "by_tier": {}, "by_domain": {}}
    
    by_source = {}
    by_tier = {"Top Tier": 0, "Solid": 0, "Low Priority": 0}
    by_domain = {}
    
    for h in db:
        # By source
        source = h.get("source_platform", "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        
        # By tier
        tier = h.get("score_tier", "Low Priority")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        
        # By domain
        for domain in h.get("domains", []):
            by_domain[domain] = by_domain.get(domain, 0) + 1
    
    return {
        "total": len(db),
        "by_source": by_source,
        "by_tier": by_tier,
        "by_domain": by_domain
    }