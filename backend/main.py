"""
Hackfolio FastAPI Backend
Main application entry point with in-memory data store (MongoDB to be added later)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.routes import hackathons
from backend.routes import health
from backend.db import set_hackathons_db, clear_hackathons_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - load data on startup."""
    # Load and score all hackathons on startup
    print("Loading hackathon data...")
    from pipeline.scorer import ImpactScorer
    from pipeline.dedupe import HackathonDeduplicator
    from scrapers.devpost_client import fetch_devpost_hackathons, normalize_devpost
    from scrapers.mlh_client import fetch_mlh_events, normalize_mlh
    from scrapers.topcoder_client import fetch_topcoder_challenges, normalize_topcoder
    from scrapers.kaggle_client import fetch_kaggle_competitions, normalize_kaggle
    from scrapers.seed_loader import load_seed_companies
    
    # Fetch from all sources
    # Devpost: use status=open filter to get only currently active hackathons (~58 total)
    devpost_raw = fetch_devpost_hackathons()
    devpost_events = normalize_devpost(devpost_raw)
    print(f"  Devpost: {len(devpost_events)} events")
    
    mlh_raw = fetch_mlh_events()
    mlh_events = normalize_mlh(mlh_raw)
    print(f"  MLH: {len(mlh_events)} events")
    
    topcoder_raw = fetch_topcoder_challenges()
    topcoder_events = normalize_topcoder(topcoder_raw)
    print(f"  Topcoder: {len(topcoder_events)} events")
    
    kaggle_raw = fetch_kaggle_competitions()
    kaggle_events = normalize_kaggle(kaggle_raw)
    print(f"  Kaggle: {len(kaggle_events)} events")
    
    seed_events = load_seed_companies()
    print(f"  Seed companies: {len(seed_events)} events")
    
    # Combine all events
    all_events = devpost_events + mlh_events + topcoder_events + kaggle_events + seed_events
    print(f"  Total before dedupe: {len(all_events)}")
    
    # Deduplicate
    deduplicator = HackathonDeduplicator()
    deduped_events = deduplicator.deduplicate(all_events)
    print(f"  Total after dedupe: {len(deduped_events)}")
    
    # Score all events
    scorer = ImpactScorer()
    scored_events = scorer.score_events(deduped_events)
    print(f"  Scored {len(scored_events)} events")
    
    set_hackathons_db(scored_events)
    print("Data loading complete!")
    
    yield
    
    # Cleanup on shutdown
    clear_hackathons_db()


app = FastAPI(
    title="Hackfolio API",
    description="Curated hackathon discovery and tracking API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(hackathons.router, prefix="/api", tags=["hackathons"])


@app.get("/")
async def root():
    return {
        "name": "Hackfolio API",
        "version": "0.1.0",
        "description": "Curated hackathon discovery and tracking API",
        "docs": "/docs"
    }