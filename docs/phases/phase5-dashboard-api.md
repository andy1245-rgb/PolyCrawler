# Phase 5 — Dashboard API

**Source:** spec.md §16.5, §11, §12 | docs/architecture.md §10
**Status:** ⬜ Not started
**Prerequisites:** [Phase 4](phase4-reconciliation.md) complete (can start in parallel — routes don't depend on reconciliation)

---

## Goal

Build FastAPI routes that expose the crawler's data to a dashboard frontend. Alerts, positions, sessions, and config are all queryable. The false-positive labeling button works. This phase makes the system observable without reading raw DB tables.

## Spec references

- spec §11 — Alerts (dashboard is the only alert surface in v0.1.0)
- spec §12 — Sessions & analytics (session lifecycle, global analytics, inclusion toggles)
- spec §12.3 — Data to persist (false-positive labels, analytics-first)
- arch §10 — API layer (routes, stack, app factory)

## Prerequisites

- Phase 3b complete: `paper_trades`, `alerts`, `sessions` have real data
- FastAPI app exists in `main.py` (Phase 0)
- Can start in parallel with Phase 4 — routes read from DB, don't depend on reconciliation

## Modules to build

### 1. `src/poly_crawler/api/app.py` — FastAPI app factory

Refactor app creation out of `main.py` into a proper factory. `main.py` becomes a thin entry point.

```python
def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="PolyCrawler", version="0.1.0")
    app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
    app.include_router(positions.router, prefix="/positions", tags=["positions"])
    app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
    app.include_router(config_router.router, prefix="/config", tags=["config"])
    app.include_router(stats.router, prefix="/stats", tags=["stats"])
    return app
```

### 2. `src/poly_crawler/api/routes/alerts.py` — Alert routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/alerts` | List alerts (filter: type, parent_id, cluster_id, time range, is_false_positive) |
| GET | `/alerts/{id}` | Alert detail with related cluster/position context |
| PATCH | `/alerts/{id}` | Set `is_false_positive` (the labeling button) |

**Query parameters for GET /alerts:**

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `alert_type` | `str | None` | None | Filter by type (fund, birth, conflict, entry, exit) |
| `parent_id` | `UUID | None` | None | Filter by parent |
| `cluster_id` | `UUID | None` | None | Filter by cluster |
| `is_false_positive` | `bool | None` | None | Filter by label status |
| `limit` | `int` | 50 | Pagination |
| `offset` | `int` | 0 | Pagination |
| `sort` | `str` | "created_at desc" | Sort order |

### 3. `src/poly_crawler/api/routes/positions.py` — Position routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/positions` | List cluster positions (filter: state, cluster_id) |
| GET | `/positions/{id}` | Position detail + trade history |

**Query parameters for GET /positions:**

| Param | Type | Default | Purpose |
|-------|------|---------|---------|
| `state` | `str | None` | None | Filter by state (watching, signal, in_position, closed, skipped) |
| `cluster_id` | `UUID | None` | None | Filter by cluster |
| `limit` | `int` | 50 | Pagination |
| `offset` | `int` | 0 | Pagination |

**GET /positions/{id} response includes:**

- Position details (state, net_exposure, mirrored_yes/no, sibling_balances)
- All related `paper_trades` (entry → adjustments → exit)
- Related alerts
- Config snapshot at entry

### 4. `src/poly_crawler/api/routes/sessions.py` — Session routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/sessions` | List sessions (filter: mode, status, private) |
| POST | `/sessions` | Create a new session |
| GET | `/sessions/{id}` | Session detail + stats |
| PATCH | `/sessions/{id}` | Update session (end, toggle private) |

**POST /sessions body:**

```json
{
    "name": "Paper run 2026-06-30",
    "mode": "paper",
    "review_mode": "live_only",
    "private": false
}
```

### 5. `src/poly_crawler/api/routes/config.py` — Config routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/config` | Current runtime config (full Pydantic model) |
| PUT | `/config` | Update config (live reload — reinitializes engine) |

**Live reload behavior:**

- Validates new config with Pydantic
- Creates a new `config_snapshots` row
- Does NOT restart the engine mid-cycle — new config applies on next poll cycle
- Returns the validated config

### 6. `src/poly_crawler/api/routes/stats.py` — Analytics routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/stats/global` | Global analytics rollup across selected sessions |
| GET | `/stats/sessions/{id}` | Per-session stats (PnL, trade count, win rate) |

**GET /stats/global response (basic — full analytics TBD per spec §12.2):**

```json
{
    "total_sessions": 5,
    "total_trades": 127,
    "total_pnl_usd": 342.50,
    "win_rate": 0.62,
    "avg_latency_ms": 1200,
    "active_positions": 3,
    "total_alerts": 89
}
```

### 7. `src/poly_crawler/api/schemas.py` — Pydantic response models

Define request/response schemas separate from DB models for clean API contracts.

| Model | Purpose |
|-------|---------|
| `AlertResponse` | Alert with related context |
| `AlertUpdateRequest` | `is_false_positive` toggle |
| `PositionResponse` | Position with trades + alerts |
| `PositionListResponse` | Paginated position list |
| `SessionCreateRequest` | Session creation body |
| `SessionResponse` | Session with stats |
| `ConfigResponse` | Full config dump |
| `StatsResponse` | Global analytics rollup |

### 8. Update `src/poly_crawler/main.py` — Use app factory

```python
from poly_crawler.api.app import create_app

@asynccontextmanager
async def lifespan(_app: FastAPI):
    config = load_config()
    init_engine(config)
    # ... scheduler start
    yield
    # ... scheduler stop
    await close_engine()

config = load_config()
app = create_app(config)
app.router.lifespan_context = lifespan
```

## Data flow

### Alert labeling (false-positive button)

```
1. Dashboard user clicks "Mark as false positive" on an alert
2. PATCH /alerts/{id} with body {"is_false_positive": true}
3. Route handler updates the alert row
4. Returns updated alert
5. Future GET /alerts?is_false_positive=false excludes this alert
```

### Position detail view

```
1. Dashboard requests GET /positions/{id}
2. Route handler loads ClusterPosition by id
3. Eager-loads related PaperTrades (sorted by created_at)
4. Eager-loads related Alerts
5. Loads ConfigSnapshot if config_snapshot_id is set
6. Returns PositionResponse with all nested data
```

## Config changes

None.

## DB changes

None. All tables exist. This phase only reads (and updates `alerts.is_false_positive`, `sessions` status/private).

## Test plan

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_alerts_api.py` | GET /alerts with filters; GET /alerts/{id}; PATCH false-positive toggle; pagination |
| `tests/integration/test_positions_api.py` | GET /positions with state filter; GET /positions/{id} with trades + alerts; 404 for unknown id |
| `tests/integration/test_sessions_api.py` | POST create session; GET list; PATCH end session; PATCH toggle private; GET detail with stats |
| `tests/integration/test_config_api.py` | GET /config returns full config; PUT /config validates and updates |
| `tests/integration/test_stats_api.py` | GET /stats/global returns aggregated stats; GET /stats/sessions/{id} returns per-session stats |

**Test approach:** Use FastAPI `TestClient` with the in-memory SQLite test DB from conftest. Seed test data via factory fixtures, then hit endpoints.

## Acceptance criteria

- [ ] `create_app()` factory builds FastAPI with all route groups
- [ ] GET /alerts supports all filters (type, parent, cluster, false_positive, pagination)
- [ ] PATCH /alerts/{id} toggles `is_false_positive`
- [ ] GET /positions/{id} returns position with trades + alerts + config snapshot
- [ ] POST /sessions creates a session with config snapshot
- [ ] PATCH /sessions/{id} can end session and toggle private
- [ ] GET /config returns current runtime config
- [ ] PUT /config validates and applies new config
- [ ] GET /stats/global returns aggregated stats
- [ ] All integration tests pass with TestClient + in-memory SQLite
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | Auth on API routes? | v0.1: no auth (local dashboard). Add API key or OAuth in future. |
| 2 | CORS configuration | Enable CORS for localhost if frontend is separate. Add `CORSMiddleware` to app factory. |
| 3 | WebSocket for real-time updates? | v0.1: polling only. WebSocket for live alert/position updates could be a future enhancement. |
| 4 | Full analytics (spec §12.2) | Spec says "actual analytics TBD". Basic stats (PnL, win rate, counts) for now. Full analytics in a later version. |
| 5 | Frontend framework | Spec says "TBD with user". API-first for v0.1 — frontend in a separate design pass. |
