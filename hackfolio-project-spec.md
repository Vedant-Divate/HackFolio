# Hackfolio — Project Specification

> **Purpose of this document**: This is a comprehensive technical and product specification for "Hackfolio," a curated hackathon discovery and tracking tool. It is written to be used as full context for AI coding assistants (Claude Code, Cursor, etc.) to scaffold, build, and extend the project. It includes problem framing, architecture, data models, scoring logic, feature set, and a phased build roadmap.

---

## 1. Problem Statement

Hackathon discovery today is fragmented and noisy:

- Aggregator platforms (Devfolio, Unstop, HackerEarth, Devpost) each show only their own listings — no cross-platform view.
- The vast majority of listed events are low-value: college fests, unpaid "hackathons" with no real prize, no sponsor credibility, or minimal resume impact.
- High-value **company-run hackathons** (Cisco Sparkathon, Walmart Sparkathon, Flipkart GRiD, Smart India Hackathon, Google Solution Challenge, etc.) are scattered across individual corporate portals and rarely surface on aggregators at all.
- There is no existing tool that filters hackathons by **actual resume/career impact** rather than just recency or popularity.

**Hackfolio** solves this by aggregating hackathons from 10+ major platforms plus a curated list of recurring company-run programs, scoring each one for legitimacy/impact, and surfacing only the events worth a student's time.

---

## 2. Target User

- Primary: the builder (student in AI/DS, full-stack + ML + blockchain + security background, actively hackathon-competitive, resume-driven).
- Designed for personal daily/weekly use first; architected cleanly enough to demo as a portfolio project later (recruiters, LinkedIn, GitHub).

---

## 3. Goals & Non-Goals

### Goals
- Aggregate hackathon listings from 10+ sources into one unified, deduplicated feed.
- Score/rank each hackathon by a transparent "Impact Score" so low-value events are filterable out by default.
- Support filtering by domain (AI/ML, blockchain, full-stack, security, web3, cloud), prize pool, deadline, mode (online/offline/hybrid), and organizer tier.
- Track deadlines with alerts so nothing worth applying to is missed.
- Be maintainable by one person — prefer official APIs where they exist, targeted scrapers where they don't, and manual curation for low-volume/high-value corporate hackathons.

### Non-Goals (v1)
- Not building a hackathon *hosting* platform — discovery/tracking only.
- Not attempting full coverage of every regional/college-level hackathon — quality over completeness.
- Not building real-time team-matchmaking in v1 (listed as a future feature, see §8).

---

## 4. Data Sources

### 4.1 Aggregator Platforms (10)

| # | Platform | Access Method | Reliability | Notes |
|---|----------|---------------|-------------|-------|
| 1 | Devpost | Public JSON API (`devpost.com/api/hackathons`) | High | Best prize/sponsor metadata, global coverage |
| 2 | MLH (Major League Hacking) | JSON feed on season page | High | MLH-sanctioned status is itself a strong legitimacy signal |
| 3 | Devfolio | Internal API (undocumented but stable, inspect via browser devtools/network tab) | Medium-High | Dominant for India-based college & company hackathons |
| 4 | Unstop (Dare2Compete) | Requires headless browser (Playwright) — JS SPA, plain HTTP requests return no content | Medium | High volume but noisy; needs aggressive score filtering |
| 5 | HackerEarth | HTML scrape (BeautifulSoup/lxml) | Medium | Frequently used by companies to host challenges directly |
| 6 | Kaggle Competitions | Official `kaggle` Python package / public API | High | ML/data competitions — resume-equivalent for AI/DS track, tag as separate category |
| 7 | AngelHack | HTML scrape | Medium | Global, corporate-partnered (Mastercard, Samsung, etc.) |
| 8 | Topcoder | Public API | High | Strong for algorithmic/security challenges |
| 9 | Hackathon.com / DevNetwork | HTML scrape | Low-Medium | Older listings source, still catches enterprise events others miss |
| 10 | Junction | HTML/API hybrid | Medium | Europe's largest hackathon org, high prestige for international resume lines |

### 4.2 Curated Company Seed List (manual, quarterly review)

Stored as a structured config file (`seed_companies.yaml`), not scraped — corporate portal layouts change unpredictably and volume is low enough that manual review beats fragile scrapers.

Each entry carries a `category_tags` field so the scoring/filtering layer can distinguish event types (e.g. a hiring-linked pipeline event vs. a pure-prestige competition vs. a social-impact challenge). Suggested tag vocabulary: `placement_pipeline`, `prestige`, `web3`, `social_impact`, `women_focused`, `research_linked`, `fintech`.

#### India-focused corporate hackathons / hiring pipelines

| Company | Program | Tags | Notes |
|---|---|---|---|
| Cisco | Sparkathon / Global Problem Solver Challenge | `prestige` | |
| Walmart | Sparkathon | `placement_pipeline`, `prestige` | High CTC/stipend hiring pipeline |
| Walmart | CodeHers | `placement_pipeline`, `women_focused` | Women-focused track, separate from Sparkathon |
| Flipkart | GRiD | `placement_pipeline`, `prestige` | Stipends up to ₹1L/month, CTC up to ₹32.67L reported for recent editions |
| Amazon | HackOn | `placement_pipeline` | Direct hiring-linked hackathon, distinct from AWS's Devpost-hosted challenges |
| Amazon (AWS) | AWS hackathons | `prestige` | Usually hosted via Devpost |
| Adobe | India Hackathon | `prestige` | |
| Goldman Sachs | Technical hackathons | `placement_pipeline`, `fintech` | High CTC signal even for non-finance roles |
| Google | Solution Challenge / Cloud hackathons | `prestige`, `social_impact` | |
| Microsoft | Imagine Cup | `prestige` | One of the most valuable global student competitions, strong startup/mentorship angle |
| Mastercard | e.g. GFF AI Defense Lab | `prestige`, `fintech` | See prior FraudGuard 360 work |
| Cognizant | Student Hackathon | `placement_pipeline` | Pre-placement track |
| Infosys / TCS / Wipro / Bajaj Finserv / Tata | Various hiring-linked hackathons & coding challenges | `placement_pipeline` | Lower prestige than product companies but very high placement conversion — track separately from prestige-tagged events |
| Samsung | PRISM / EnnovateX | `research_linked` | R&D-driven, strong fit for ML/embedded projects |
| Smart India Hackathon (SIH) | — | `prestige`, `social_impact` | Government-run, extremely high resume value in India |

#### Global corporate / foundation hackathons

| Company / Org | Program | Tags | Notes |
|---|---|---|---|
| NASA | Space Apps Challenge | `prestige`, `social_impact` | Major global hackathon, free datasets/APIs provided, strong international resume weight |
| Ethereum Foundation / ETHGlobal | ETHGlobal series | `web3`, `prestige` | Leading global blockchain/web3 hackathon series — direct match to LinkPe/Solidity work |
| IBM | Call for Code | `social_impact`, `prestige` | Global social-impact challenge, strong enterprise credibility |
| Meta | Hacker Cup / dev challenges | `prestige` | Occasional, algorithmic-challenge flavored |
| JPMorgan Chase | Code for Good | `social_impact`, `fintech`, `placement_pipeline` | High prestige, finance + social impact combo |
| Salesforce | TrailblazerDX hackathons | `prestige` | |
| VMware / Qualcomm | Occasional hardware/systems challenges | `research_linked` | Good fit if pivoting toward embedded/IoT |
| Barclays / Deutsche Bank | Fintech hackathons | `fintech`, `placement_pipeline` | Decent blockchain crossover potential |
| Major League Hacking | Global season (year-round, not single event) | `prestige` | Track as an ongoing program rather than a dated event — needs different ingestion handling than one-off hackathons |

### 4.3 Source Reliability Tiering

Each source is tagged `api` / `scrape_html` / `scrape_js` / `manual_seed` in the ingestion config, so the pipeline knows expected fragility and can alert if a source silently returns zero results (likely a broken selector).

---

## 5. Impact Scoring Algorithm — Core Differentiator

Every ingested hackathon gets a computed **Impact Score (0–100)**. This is the core value proposition: filtering "hackathons that exist" down to "hackathons that matter."

### 5.1 Scoring Factors

| Factor | Weight | Logic |
|---|---|---|
| Organizer tier | 25% | MLH-sanctioned / Major League Hacking partner / known platform-featured event = high; unrecognized college fest = low |
| Sponsor brand recognition | 20% | Match sponsor list against a curated "recognized brands" list (FAANG, major Indian unicorns, Fortune 500). More recognized sponsors = higher score |
| Prize pool | 20% | Normalized against a configurable floor/ceiling (e.g. ₹50,000 floor for "counts," scaled up to large international prize pools) |
| Domain/stack match | 15% | Self-tagged relevance to the user's stack (AI/ML, blockchain, full-stack, security) — configurable per user profile |
| Participation scale | 10% | Registered participant/team count where available — proxy for legitimacy and networking value |
| Recency/activity | 10% | Penalize listings with stale or ambiguous dates; boost active, currently-open applications |

### 5.2 Scoring Output

- **Score ≥ 75**: "Top Tier" — auto-surfaced, notification-worthy
- **Score 50–74**: "Solid" — shown by default, filterable
- **Score < 50**: "Low Priority" — hidden by default, visible via "show all" toggle

Scoring weights should live in a single config file (`scoring_config.yaml`) so they can be tuned without code changes.

### 5.3 Deduplication

Since Devfolio/Unstop/HackerEarth often list overlapping company hackathons, dedupe by fuzzy-matching on (event name + date window + organizer), using something like `rapidfuzz` for string similarity. Keep the version with the most complete metadata (usually the official platform, not a reposting).

---

## 6. System Architecture

```
hackfolio/
├── scrapers/                      # Python — one module per source
│   ├── devpost_client.py          # API-based
│   ├── mlh_client.py              # API-based
│   ├── devfolio_client.py         # API-based (reverse-engineered)
│   ├── unstop_scraper.py          # Playwright (JS-rendered)
│   ├── hackerearth_scraper.py     # BeautifulSoup
│   ├── kaggle_client.py           # Official API package
│   ├── angelhack_scraper.py       # BeautifulSoup
│   ├── topcoder_client.py         # API-based
│   ├── devnetwork_scraper.py      # BeautifulSoup
│   ├── junction_client.py         # API/HTML hybrid
│   └── seed_companies.yaml        # Manually curated corporate hackathons
│
├── pipeline/                      # Ingestion orchestration
│   ├── run_ingestion.py           # Entry point, runs all scrapers
│   ├── dedupe.py                  # Fuzzy-match dedup logic
│   ├── scorer.py                  # Impact score calculation
│   ├── scoring_config.yaml
│   └── normalizer.py              # Maps each source's raw schema → unified schema
│
├── backend/                       # FastAPI
│   ├── main.py
│   ├── models/                    # Pydantic + DB models
│   ├── routes/
│   │   ├── hackathons.py          # GET/filter endpoints
│   │   ├── alerts.py              # Deadline alert subscriptions
│   │   └── bookmarks.py           # Saved hackathons
│   └── db/                        # MongoDB or MySQL connector
│
├── frontend/                      # React + Vite
│   ├── src/
│   │   ├── components/
│   │   │   ├── HackathonCard.tsx
│   │   │   ├── FilterPanel.tsx
│   │   │   ├── ScoreBadge.tsx
│   │   │   └── DeadlineCalendar.tsx
│   │   └── pages/
│   │       ├── Dashboard.tsx
│   │       ├── Bookmarks.tsx
│   │       └── Analytics.tsx
│
├── infra/
│   ├── Dockerfile (backend + frontend)
│   ├── docker-compose.yml
│   └── .github/workflows/
│       ├── ingest-cron.yml        # Scheduled scraper run (e.g. daily)
│       └── deploy.yml             # CI/CD to Render/Vercel
│
└── docs/
    └── this file
```

### 6.1 Tech Stack (matches existing toolchain for consistency)

- **Backend**: Python, FastAPI
- **Frontend**: React + Vite
- **Database**: MongoDB (flexible schema fits varied source data better than relational; alternative: MySQL if normalized schema preferred)
- **Scraping**: `requests` + `BeautifulSoup` for static HTML, `Playwright` for JS-rendered (Unstop)
- **Scheduling**: GitHub Actions cron job (daily ingestion run)
- **Deployment**: Backend on Render, frontend on Vercel (same pattern as LinkPe)
- **Containerization**: Docker + Docker Compose for local dev parity

---

## 7. Unified Data Model

All source-specific data gets normalized into one schema before storage:

```json
{
  "id": "uuid",
  "title": "string",
  "organizer": "string",
  "source_platform": "devpost | mlh | devfolio | unstop | hackerearth | kaggle | angelhack | topcoder | devnetwork | junction | manual",
  "source_url": "string",
  "description": "string",
  "domains": ["ai_ml", "blockchain", "full_stack", "security", "web3", "cloud"],
  "mode": "online | offline | hybrid",
  "location": "string | null",
  "prize_pool": {
    "amount": "number",
    "currency": "string",
    "display_text": "string"
  },
  "sponsors": ["string"],
  "registration_deadline": "ISO8601 datetime",
  "event_start_date": "ISO8601 datetime",
  "event_end_date": "ISO8601 datetime",
  "participant_count": "number | null",
  "impact_score": "number (0-100)",
  "score_breakdown": {
    "organizer_tier": "number",
    "sponsor_recognition": "number",
    "prize_pool": "number",
    "domain_match": "number",
    "participation_scale": "number",
    "recency": "number"
  },
  "tags": ["string"],
  "is_mlh_sanctioned": "boolean",
  "ingested_at": "ISO8601 datetime",
  "last_updated_at": "ISO8601 datetime"
}
```

---

## 8. Feature Set

### 8.1 Core Features (v1 — MVP)
- Multi-source ingestion pipeline (10 platforms + manual seed list)
- Deduplication across sources
- Impact Score computation and display
- Filterable/sortable dashboard (by score, deadline, domain, prize, mode)
- Deadline countdown per hackathon card
- Bookmarking / saved list

### 8.2 High-Value Additions (v1.5 — recommended)
- **Deadline alerts**: email or Telegram/Discord bot notification X days before registration closes for bookmarked or high-score hackathons.
- **Personal Application Tracker**: track status per hackathon — `interested → applied → shortlisted → participating → submitted → result`. Useful for your own resume/portfolio recordkeeping (you already track things like FraudGuard member responsibilities this granularly).
- **Calendar export**: `.ics` file generation or Google Calendar sync for registration deadlines and event dates.
- **Domain auto-tagging via NLP**: instead of relying purely on manual/source tags, run hackathon descriptions through a lightweight classifier (or Groq/Gemini call with structured output, consistent with your existing `ChatGroq` + `with_structured_output()` pattern) to auto-tag domains from free text.
- **"Matches your stack" highlighting**: since you maintain a structured skills list, cross-reference hackathon required/preferred tech against it and visually highlight strong matches.
- **Analytics dashboard**: track your own hackathon participation history over time — number applied vs. won/placed, domains competed in, cumulative "impact" of hackathons you've actually done. Doubles as resume-evidence generation.

### 8.3 Stretch Features (v2+)
- **Browser extension**: quick "save to Hackfolio" button while browsing Devfolio/Unstop directly.
- **Public leaderboard/community layer**: if ever opened beyond personal use, let other students submit/upvote hackathons, with your scoring algorithm as the ranking backbone (this is the differentiator vs. plain crowdsourced lists).
- **Team-finder integration**: optional matching with other users looking for teammates in specific domains — bigger scope, only if project expands beyond personal tool.
- **Historical prize-pool trend analysis**: track how prize pools/participation for recurring events (e.g. Smart India Hackathon, Cisco Sparkathon) change year over year, useful for deciding where to invest prep time.
- **GitHub-aware recommendations**: pull your own GitHub repo languages/topics and auto-boost domain-match scoring based on what you're actually actively building, rather than a static self-tagged profile.
- **Resume bullet generator**: for hackathons marked "won/placed" in the tracker, auto-draft a resume bullet in your established format/tone, consistent with prior resume work.

---

## 9. API Design (Backend)

### Core Endpoints

```
GET  /api/hackathons
     ?domain=ai_ml,blockchain
     &min_score=50
     &mode=online
     &deadline_before=2026-12-31
     &sort=score_desc | deadline_asc | prize_desc

GET  /api/hackathons/{id}

POST /api/bookmarks/{hackathon_id}
DELETE /api/bookmarks/{hackathon_id}
GET  /api/bookmarks

POST /api/tracker/{hackathon_id}
     { "status": "applied" | "shortlisted" | "participating" | "submitted" | "won" | "placed" }
GET  /api/tracker

GET  /api/analytics/summary
     -> { total_applied, total_won, domains_breakdown, avg_impact_score_of_applied }

POST /api/alerts/subscribe
     { "hackathon_id": "...", "days_before": 3, "channel": "email" | "telegram" | "discord" }
```

---

## 10. Ingestion Pipeline Details

1. **Scheduled trigger**: GitHub Actions cron (e.g. once daily, off-peak).
2. **Per-source fetch**: each scraper module runs independently, wrapped in try/except so one source failing doesn't block others; failures logged and optionally alerted.
3. **Normalization**: raw per-source data mapped to the unified schema (§7).
4. **Deduplication**: fuzzy match against existing DB entries (name + date window + organizer similarity).
5. **Scoring**: run Impact Score calculation on new/updated entries.
6. **Upsert**: write to DB, updating `last_updated_at` for existing entries (e.g. if a deadline gets extended).
7. **Alerting**: check bookmarked/high-score entries against alert subscriptions, dispatch notifications.

### Resilience notes
- Each scraper should have a "sanity check" — if it returns zero results where historically it returns dozens, treat as a likely broken selector/API change and alert rather than silently ingesting nothing (this is a known failure mode in JS-SPA scraping — Unstop's site structure has already been observed to break plain HTTP fetching entirely).
- Rate-limit scrapers respectfully; add delays between requests especially for HTML-scraped sources.

---

## 11. Build Roadmap

### Phase 1 — Foundation (Week 1)
- Devpost + MLH + Topcoder + Kaggle clients (all have real APIs — fastest wins)
- Unified schema + normalizer
- Raw JSON output, no DB yet — validate data quality first

### Phase 2 — Core Pipeline (Week 2)
- Scoring engine + `scoring_config.yaml`
- Deduplication logic
- MongoDB integration
- Manual seed company list (`seed_companies.yaml`)
- Basic FastAPI `/hackathons` endpoint — usable by you at this point

### Phase 3 — Remaining Sources (Week 3)
- Devfolio, HackerEarth, AngelHack, DevNetwork, Junction scrapers
- Cross-source dedupe validation
- Alert subscription backend

### Phase 4 — Frontend + Hardest Source (Week 4)
- Unstop via Playwright (hardest, intentionally last)
- React dashboard: filter panel, score badges, deadline calendar view
- Bookmarking UI

### Phase 5 — Polish & Deploy (Week 5+)
- GitHub Actions cron for scheduled ingestion
- Docker + deploy (Render backend, Vercel frontend)
- Application Tracker + Analytics dashboard
- Deadline notification channel (email or Telegram bot)

---

## 12. Portfolio/Resume Framing (for later)

Once built to a demo-ready state, this project is a strong resume line because it demonstrates:
- Multi-source data pipeline engineering (API integration + web scraping + browser automation)
- Data normalization and fuzzy deduplication at scale
- A defensible, explainable scoring/ranking algorithm (not just a CRUD listing app)
- Full-stack ownership: Python backend, React frontend, MongoDB, Docker, CI/CD
- Solo-built, clearly attributable — matches your established preference for individually-ownable resume projects (as with LinkPe over ScholarStream)

Suggested resume bullet draft (to refine once built):
> "Built a full-stack hackathon aggregation platform ingesting and scoring 10+ data sources via APIs, headless-browser, and HTML scraping, deduplicating results with fuzzy matching and ranking events with a custom multi-factor legitimacy/impact algorithm."

---

## 13. Open Questions / Decisions Needed Before Build

- **Database choice**: MongoDB (flexible, faster to iterate) vs MySQL (consistent with CodeAlpha stack, more structure). Recommendation: MongoDB for this specific project given heterogeneous source schemas.
- **Notification channel**: Telegram bot (simple, free, good for personal use) vs email (more "professional" if this becomes a public-facing project later).
- **Hosting for scheduled scraping**: GitHub Actions cron (free, simple) vs a small always-on VM (Oracle Cloud free tier is already in your toolkit) if scraping needs grow beyond GitHub Actions' execution time limits.
- **Public vs private**: stays a personal tool with public GitHub repo (for resume visibility) vs eventually opening it to other students as a small SaaS/community tool (stretch goal, §8.3).
