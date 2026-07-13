# PolyCrawler — Session Handoff TODO
 
> **Created:** 2026-07-13  
> **Purpose:** Capture all discussion topics from the doc-restructure review session. **Do not start implementation until each section is reviewed and agreed.**  
> **Branch context:** `cursor/todo-discussion-cleanup-fed6` (from `cursor/doc-restructure-phases-1947`) — Phase 0 complete, Phase 1 next.
>
> **2026-07-13 session:** Restored this file (was never committed). Decisions locked below. Cleanup done. **Phase 1 (manual seed) implemented** — next review checkpoint before Phase 2.

---

## Session decisions (LOCKED 2026-07-13)

| Question | Decision | Rationale |
|----------|----------|-----------|
| Keep 11 tables at Phase 0 or reduce? | **A — Keep all 11** | Already migrated; empty Postgres tables cost ~nothing; splitting now is churn with zero feature gain. Future *new* tables can still ship per-phase. |
| Delete `rpc_logs` table or keep? | **Keep** | Spec needs SQL-queryable RPC audit for rate-limit debugging; structured logs alone are harder to join with alerts. |
| Merge `clusters` into `parents`? | **No — keep separate** | Parent = chain wallet identity; cluster = scored sibling group. 1:1 today, but scoring/analytics stay cleaner on their own table. |
| Score tuning: CLI only or GUI in Phase 5? | **CLI Phase 2 + GUI Phase 5** | CLI `score preview` for validation first; dashboard sliders when API exists. Score never gates entry. |
| Config override: file vs DB for slider changes? | **`local.yaml` persist + DB session override** | File for durable operator prefs; `config_snapshots` / session row for run-scoped experiments. |
| Proceed with `spec-full.md` deletion? | **Yes — after migrating blockers** | Blockers found: §7.5 hedge examples, `alert_only` policy, `tp_sl_*` rename, exit reason names, cross-refs. |
| Phase doc template | **Keep as standard** | Confirmed — no structural change. |
| `tp_sl_*` column name | **`tp_sl_mirror_suspended_until_flat`** | Sync ORM + Alembic `0001_initial` + all docs (bootstrap not yet in production). |

### Discussion conclusions (sections 4–8)

**§4 Tables:** Option B (phase-scoped) is pedagogically nicer but rewriting Phase 0 mid-stream buys nothing. Keep 11; when teaching, use the tier A/B/C/D table in this doc as the mental model of *when rows first appear*.

**§5 Architecture:** Poll loop + two adapters is the whole system. TS analogies (interface / Zod / Prisma migrate) stand. No new beginners doc unless requested — `architecture.md` + this section is enough for Phase 1.

**§6 Score:** Discovery ranking only. Weights already in `config/schema.py` (`discovery.weights.*`, `efficiency_cap`, `profit_formula`). GUI/CLI are Phase 2/5/6 work items, not Phase 0 cleanup.

**§7 NoOp:** Stub `ExecutionAdapter` for Phase 3a so FSM/rules/net tests run without orderbook. Swap to Paper (3b) then Live (8) by injection only. Optional in-memory `actions_log` for tests — adopt when implementing 3a.

**§8 Rename:** One name everywhere: `tp_sl_mirror_suspended_until_flat`. Config key stays snake `tp_sl_suspend_mirror_until_flat` (YAML/env style).

---

## Quick summary of what the user asked for

| # | Topic | Action type |
|---|--------|-------------|
| 1 | README should match final doc model (no archived spec link) | Edit |
| 2 | Delete `docs/reference/spec-full.md` after verifying all content migrated | Delete + update ~25 cross-refs |
| 3 | Keep behavioral fixes: `CLOSED` bookkeeping, `tp_sl_mirror_suspended_until_flat` rename | Preserve in phase docs + code migration |
| 4 | Phase doc template — user likes it; keep as standard | No change (confirm) |
| 5 | Phase 0: are all 11 DB tables needed at once? Explain + discuss reduction | Discussion → possible schema change |
| 6 | Full architecture walkthrough (user: SQL/TS background, light on DB-in-code) | Discussion / doc |
| 7 | Score formula review + GUI sliders / CLI commands to tune weights | Design + future Phase 5/6 work |
| 8 | `NoOpExecutionAdapter` — full explanation | Discussion / doc |

---

## 1. README — align with post-archive doc model

### Status: ✅ DONE (2026-07-13)

README now reflects the two-layer doc model only (no `spec-full` row). How-to-develop block added. Score formula points to clustering.md / phase2.

---

## 2. Delete archived spec (`spec-full.md`)

### Status: ✅ DONE (2026-07-13)

- Migrated §7.5 hedge worked examples + `alert_only` policy into `entry-rules.md`
- Aligned exit close reasons + TP/SL suspend semantics in `exit-rules.md`
- Expanded FSM domain doc (CLOSED bookkeeping, `tp_sl_mirror_suspended_until_flat`)
- Renamed ORM + Alembic `0001_initial` column
- Deleted `docs/reference/spec-full.md`; zero remaining file refs outside this todo

### Before deleting — verification checklist (completed)

#### Behavioral content (must live in phase docs)

| Original spec section | Migrated to | Verified? |
|----------------------|-------------|-----------|
| §1 Purpose | `docs/overview/purpose.md`, `spec.md` index | ✅ |
| §2 Glossary | `docs/overview/glossary.md` | ✅ |
| §3 Account types | `docs/overview/account-types.md`, `phase2` behavioral spec | ✅ |
| §4 Cluster score | `docs/discovery/clustering.md`, `phase2` behavioral spec | ✅ |
| §5 Protocol 1 (FUND/BIRTH) | `docs/discovery/new-account-detection.md`, `phase2` | ✅ |
| §6 Protocol 2 (FSM) | `docs/protocols/position-state-machine.md`, `phase3a-fsm-and-net.md` | ✅ |
| §7 Protocol 3 (Entry) | `docs/protocols/entry-rules.md` (incl. §7.5/7.7), `phase3a-trading-rules.md` | ✅ |
| §8 Protocol 4 (Exit) | `docs/protocols/exit-rules.md`, `phase3a-trading-rules.md` | ✅ |
| §9 Protocol 5 (Review) | `docs/protocols/review-and-autonomy.md`, `phase3a-trading-rules.md` | ✅ |
| §10 Paper fill model | `docs/execution/paper-fill-model.md`, `phase3b` | ✅ |
| §11–13 Operations / alerts / sessions | `docs/operations/*`, phase 5 | ✅ |
| §14 Config | `docs/reference/configuration.md` | ✅ |
| §15–16 Build order / phases | `docs/phases/_index.md`, `implementation-phases.md` | ✅ |
| §17–18 Analytics / API | `phase5`, `phase6`, `api-routes.md` | ✅ |
| §19 DB schema | `docs/reference/database-schema.md`, `architecture.md` §2 | ✅ |
| §20–21 Tech stack / history | `tech-stack.md`, `document-history.md` | ✅ |

#### Fixes that MUST survive deletion

| Fix | Where it must live | Code synced? |
|-----|-------------------|--------------|
| **`CLOSED` is bookkeeping only** — exit logged, then same tick → `WATCHING` | `phase3a-fsm-and-net.md`, `position-state-machine.md` | ✅ Docs; FSM not built yet |
| **Field rename:** `tp_sl_suspended` → `tp_sl_mirror_suspended_until_flat` | Phase docs, ORM, Alembic, schema docs | ✅ Synced |

---

## 3. Phase doc template — keep as standard

User likes the template introduced in the restructure. **No structural change needed.**

### Standard sections (confirm for all future phases)

1. **Goal** — one paragraph
2. **Behavioral specification** — self-contained rules (no external spec file)
3. **Implementation** — modules, interfaces, data flow
4. **Config / DB changes**
5. **Test plan**
6. **Acceptance criteria** (checkboxes)
7. **Human-readable docs** (links)
8. **Open decisions** (table)

### Optional improvement (discuss)

- Add a **"Prerequisites verified"** mini-checklist at top of each phase doc.
- Phase 0 doc could note which tables are **created empty** vs **first written** in later phases (ties to task 5).

---

## 4. Phase 0 — all 11 DB tables: explain + reduce?

### Context for discussion

Phase 0 created **all 11 tables upfront** via Alembic even though most stay empty until Phases 2–6. User wants to understand each table and whether creating them all at bootstrap is necessary or overkill.

**How DB-in-code works here (plain English):**

- **SQLAlchemy ORM** = Python classes that map to SQL tables (`Parent` class ↔ `parents` table).
- **Alembic** = migration tool. Each migration is a versioned script that runs `CREATE TABLE` / `ALTER TABLE`. `alembic upgrade head` applies them in order.
- **Async engine** (`asyncpg`) = app opens connections, runs queries without blocking the event loop.
- **Repositories** (Phase 1+) = thin functions that run INSERT/SELECT using ORM models — you rarely write raw SQL.

Creating tables early does **not** mean you must use them early. Empty tables cost almost nothing in Postgres. The tradeoff is **schema stability** vs **incremental complexity**.

---

### Table-by-table breakdown

#### Tier A — needed by Phase 1 (manual seed)

| Table | What it stores | First used | Could defer? |
|-------|----------------|------------|--------------|
| **`parents`** | On-chain wallet addresses you flag to watch (`chain_address`, `is_ignored`) | Phase 1 CLI seed | **No** — core entity |
| **`clusters`** | 1:1 with parent; holds `cluster_score`, `sibling_count` | Phase 1 (created with parent, score=0) | **Debatable** — could merge into `parents` as columns, but separates "wallet" from "scored group" |

**Minimum for Phase 1:** 2 tables (`parents` + `clusters`), or 1 if merged.

---

#### Tier B — needed by Phase 2 (parent watcher)

| Table | What it stores | First used | Could defer? |
|-------|----------------|------------|--------------|
| **`accounts`** | Polymarket sibling accounts linked to a parent (`watch_status`, `account_type`) | Phase 2 FUND/BIRTH events | Yes — defer to Phase 2 migration |
| **`alerts`** | FUND, BIRTH, CONFLICT, entry/exit signal log for dashboard | Phase 2 | Yes — defer to Phase 2 |
| **`rpc_logs`** | Every Polygon RPC call (debugging, rate limits) | Phase 2 polling | Yes — defer to Phase 2 (or skip table → structured logging only?) |

---

#### Tier C — needed by Phase 3a/3b (engine + paper trading)

| Table | What it stores | First used | Could defer? |
|-------|----------------|------------|--------------|
| **`cluster_positions`** | Per-cluster per-market FSM state (`watching`/`in_position`/…), net exposure, mirrored shares, sibling balances JSON | Phase 3a | Yes — defer to Phase 3a migration |
| **`paper_trades`** | Every simulated fill (entry, net_adjustment, exit) with VWAP, slippage | Phase 3b | Yes — defer to Phase 3b |
| **`sessions`** | A bounded run (paper/live/backtest) with frozen config copy | Phase 3b | Yes — defer to Phase 3b |
| **`config_snapshots`** | Immutable config JSON linked to positions at entry time | Phase 3b (or 3a if storing snapshot on first signal) | Yes — defer |

---

#### Tier D — needed by Phase 4+ (reconciliation, analytics, backtest)

| Table | What it stores | First used | Could defer? |
|-------|----------------|------------|--------------|
| **`sibling_balance_snapshots`** | Point-in-time Yes/No balances per account per market per poll | Phase 4 reconciliation / analytics | **Strong defer candidate** — heaviest write volume; not needed until reconciliation |
| **`backtest_runs`** | Metadata for historical replay runs | Phase 6 | Yes — defer to Phase 6 |

---

### Reduction options (discuss together)

| Option | Tables at Phase 0 | Pros | Cons |
|--------|-------------------|------|------|
| **A. Keep all 11 (current)** | 11 | One migration; ORM models all importable; no migration churn during dev | Looks heavy; empty tables until late phases |
| **B. Phase-scoped migrations** | 2 at P0 (`parents`, `clusters`); add 3 at P2; add 4 at P3; add 2 at P4/P6 | Schema grows with features; easier mental model | More Alembic files; must update Phase 0 docs |
| **C. Merge entities** | e.g. `clusters` into `parents`; drop `config_snapshots` → use JSONB on `sessions` only | Fewer tables | Loses normalization; harder to query "config at entry" |
| **D. Drop `rpc_logs` table** | 10 tables | Use file/structured logs instead | Lose SQL-queryable RPC audit trail spec requires |

### Recommendation to discuss (not decided)

- **Phase 0 minimum viable:** `parents` + `clusters` only (Option B).
- **Strong defer:** `sibling_balance_snapshots`, `backtest_runs`, `rpc_logs` (if logging alternative OK).
- **Keep combined:** `cluster_positions` + `paper_trades` + `sessions` ship together in Phase 3 migration (engine needs positions before trades).

### Open questions for user

1. Does seeing 11 empty tables in Postgres bother you, or is the concern about **complexity of understanding**?
2. Are you OK with multiple Alembic migrations per phase, or prefer one big bootstrap migration?
3. Is `rpc_logs` as a **table** important, or would application logs suffice for v0.1?
4. Should `clusters` stay separate from `parents`, or merge into one table?

### If reducing — code impact

- [ ] New Alembic migration(s) — split `0001_initial.py` or add `0002_phase2_tables.py` etc.
- [ ] Update `phase0-bootstrap.md` behavioral spec + acceptance criteria
- [ ] Update `database-schema.md`, `architecture.md` §2
- [ ] Grep tests/conftest for table assumptions

---

## 5. Architecture — full walkthrough

> For someone comfortable with SQL and TypeScript but new to **databases inside application code**.

### 5.1 The big picture (one paragraph)

PolyCrawler is a **poll loop**: read chain/API events → update cluster state → decide enter/exit/adjust → optionally execute (paper or live) → persist everything for analytics. Two **adapter interfaces** isolate swapping data sources (polling vs WebSocket) and execution (paper vs live) without rewriting the engine.

### 5.2 Layer diagram

```
┌─────────────────────────────────────────────────────────────┐
│  CLI / FastAPI (Phase 1, 5)                                  │
│  seed parents, dashboard, config API                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Scheduler (Phase 2) — asyncio periodic tasks                 │
│  parent_watcher every 300s, score recalc, reconciliation      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Engine (Phase 3a) — brain                                    │
│  processor → state_machine → entry/exit/hedge/reentry rules   │
│  net_calculator (pure math)                                   │
└───────┬──────────────────────────────────────┬───────────────┘
        │                                      │
        ▼                                      ▼
┌───────────────────┐              ┌───────────────────────────┐
│ IngestionAdapter  │              │ ExecutionAdapter          │
│ (Phase 2 polling) │              │ NoOp → Paper (3b) → Live(8)│
│ poll_batch()      │              │ execute_entry/exit()      │
│ fetch_balances()  │              └───────────────────────────┘
│ fetch_orderbook() │
└─────────┬─────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL (SQLAlchemy async)                                │
│  parents, accounts, clusters, positions, trades, alerts, …    │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Data flow — one FUND event end-to-end

1. **Scheduler** fires `parent_watcher` task.
2. **PollingIngestionAdapter** calls Polygon RPC + Polymarket Data API.
3. **event_detector** recognizes a USDC transfer from seeded parent → new account → emits `RawEvent(type=fund)`.
4. **Engine.processor** (Phase 3a+) or ingestion-only handler (Phase 2): writes `accounts` row, `alerts` row, recalculates `clusters.cluster_score`.
5. Scanners keep polling that account for trades.
6. On first trade in a market: lazy-create `cluster_positions` row, FSM → `WATCHING` or `IN_POSITION`.
7. **entry_rules** check min USD, max odds, review mode.
8. **ExecutionAdapter** fills (paper: orderbook walk; Phase 3a stub: no-op).
9. **paper_trades** + `sessions` record the outcome.

### 5.4 Key design patterns (TS analogy)

| Python concept | TypeScript analogy |
|----------------|-------------------|
| `IngestionAdapter` ABC | Interface `IIngestionAdapter` — swap mock in tests |
| `ExecutionAdapter` ABC | Interface `IExecutionAdapter` — `PaperAdapter` \| `LiveAdapter` |
| Pydantic `Config` | Zod schema for runtime validation |
| SQLAlchemy `Mapped` models | Prisma models / Drizzle schema |
| Alembic migration | Prisma migrate / Drizzle kit |
| `async def` + `await` | `async/await` — same idea |
| Repository functions | DAO / service layer — no ORM in route handlers |

### 5.5 Config load chain

```
default.yaml  →  env vars (POLY_*)  →  optional user YAML  →  session override (DB, Phase 3b)
                     ↓
              Pydantic Config object (validated, typed)
```

### 5.6 Phase build order (critical path)

```
Phase 0 ✅ → Phase 1 (seed) → Phase 2 (watch) → Phase 3a FSM + Rules (parallel) → Phase 3b (paper) → Phase 4 (reconcile)
                                                                                      ↓
                                                              Phase 5/6/7 parallel → Phase 8 (live)
```

### Discussion tasks

- [ ] User reads `docs/architecture.md` §1–§7 with this todo as guide
- [ ] Walk through `component-interfaces.md` — confirm adapter pattern makes sense
- [ ] Optional: add `docs/overview/architecture-for-beginners.md` if user wants a permanent simplified doc

---

## 6. Cluster score formula — review + tunable GUI/CLI

### 6.1 What cluster score is (and is NOT)

**IS:** Discovery ranking, alert queue sort, analytics correlation ("did high-score clusters copy better?").

**IS NOT:** Trade entry gate. Entry uses `minBuyUsd`, `maxOdds`, review mode — never cluster score.

### 6.2 Formula (variant B — runtime default)

Per sibling account under a parent:

```python
# Only accounts with positive realized profit contribute (default vetting)
profitScore = sqrt(max(profit, 0)) * W_PROFIT

efficiencyScore = min(profit / totalDeposited, EFFICIENCY_CAP) * W_EFFICIENCY  # if deposited > 0 else 0

winRateScore = max(0, winRate - 0.5) * W_WINRATE  # only if exitCount >= minExitCount

accountWeight = profitScore + efficiencyScore + winRateScore  # losers = 0

clusterScore = sum(accountWeight for all siblings)
```

**Default weights:** `W_PROFIT=2`, `W_EFFICIENCY=15`, `W_WINRATE=5`, `EFFICIENCY_CAP=10`

**Variants (validation only until Phase 6 proves them):**

| Variant | Profit term |
|---------|-------------|
| A `log` | `log10(1 + max(profit, 0)) * W_PROFIT` |
| B `sqrt` | **default** |
| C `piecewise` | linear up to $10k, then log |

**Config keys (likely home):**

```yaml
discovery:
  profitFormula: sqrt          # sqrt | log | piecewise
  wProfit: 2
  wEfficiency: 15
  wWinrate: 5
  efficiencyCap: 10
  minExitCount: 1
  subtractLossesFromClusterScore: false
  minSiblingCount: 2
  minClusterScore: null        # Phase 7 gate — overrides minSiblingCount when set
```

⚠️ **Verify:** exact key names in `config/schema.py` and `default.yaml` match docs before building GUI.

### 6.3 User request: sliders on GUI + commands to change variables

This spans **Phase 5 (Dashboard API)** and **Phase 6 (backtesting)**.

#### Proposed UX (discuss)

| Surface | What it does | Phase |
|---------|--------------|-------|
| **CLI** | `poly-crawler config set discovery.wProfit 3` or `poly-crawler score preview --parent 0x…` | Phase 1–2 (CLI exists); score preview Phase 2 |
| **Dashboard sliders** | Adjust W_PROFIT, W_EFFICIENCY, W_WINRATE, EFFICIENCY_CAP; live preview score on labeled wallets | Phase 5 API + frontend |
| **Backtest compare** | Run same history with config A vs B; show PnL diff | Phase 6 |

#### API sketch (Phase 5)

```
GET  /config/discovery          → current weights
PATCH /config/discovery         → update weights (writes new YAML or DB override)
POST /score/preview             → { parent_id, weights? } → { cluster_score, breakdown per sibling }
POST /score/validate            → run A/B/C on labeled_wallets.json (Phase 6)
```

#### GUI slider behavior (discuss)

- Sliders change **runtime config override** (not necessarily `default.yaml` on disk).
- Show **per-component breakdown** bar chart: profit vs efficiency vs win rate per sibling.
- "Reset to defaults" button.
- Warning banner: "Score does not affect trade entry — discovery only."

### Open questions for user

1. GUI in v0.1 scope, or CLI-only until Phase 6 validation script exists?
2. Should slider changes persist to `default.yaml`, a `local.yaml` override, or DB-only session config?
3. Do you want to tune **profit formula variant** (A/B/C) via GUI or keep that CLI/backtest-only?
4. Should labeled wallet validation (`labeled_wallets.json`) be visible in the UI as a scatter plot (suspicious vs normal)?

### Tasks

- [ ] Audit `config/schema.py` for discovery weight fields — add missing keys if needed
- [ ] Document score tuning in `phase5-dashboard-api.md` behavioral spec (sliders section)
- [ ] Document `poly-crawler score` commands in `phase2` or new CLI section
- [ ] Phase 6: `validate_scoring.py` script runs A/B/C on labeled wallets

---

## 7. NoOpExecutionAdapter — full explanation

### 7.1 What problem it solves

Phase 3a builds the **engine brain** (FSM + rules + net math) **before** Phase 3b builds real paper fills. The engine always calls `ExecutionAdapter.execute_entry()` / `execute_exit()` when it decides to trade — but in Phase 3a there is no orderbook, no sessions, no `paper_trades` table writes yet.

**NoOpExecutionAdapter** = a **stub implementation** of the same interface that pretends fills succeeded without doing anything real.

### 7.2 Adapter pattern (why not just `if paper_mode` in the engine?)

```python
# BAD — engine knows too much
if config.mode == "paper":
    await paper_fill(...)
elif config.mode == "live":
    await live_fill(...)

# GOOD — engine stays dumb
result = await self.execution.execute_entry(signal)
```

Engine code is **identical** for paper and live. Only the injected adapter changes. Phase 3a injects `NoOp`; Phase 3b injects `PaperExecutionAdapter`; Phase 8 injects `LiveExecutionAdapter`.

### 7.3 What it does concretely

```python
class NoOpExecutionAdapter(ExecutionAdapter):
    async def execute_entry(self, signal: EntrySignal) -> FillResult:
        # Log signal for debugging; return fake success
        return FillResult(
            success=True,
            filled_shares=signal.shares,
            avg_price=0.0,           # no real price
            slippage_bps=0,
            book_snapshot=None,
        )

    async def execute_exit(self, signal: EntrySignal) -> FillResult:
        return FillResult(success=True, filled_shares=signal.shares, ...)
```

- **FSM still transitions** (`WATCHING` → `IN_POSITION` → `CLOSED` → `WATCHING`).
- **DB state updates** (`cluster_positions.state`, `mirrored_shares`) can still happen in the engine after the no-op returns.
- **No** `paper_trades` rows, **no** orderbook fetch, **no** session tracking — that's Phase 3b.

### 7.4 What you CAN test in Phase 3a with NoOp

| Testable | Not testable until 3b |
|----------|----------------------|
| FSM state transitions | VWAP fill price |
| Entry rules blocking/allowing | Slippage calculation |
| Exit priority chain | `paper_trades` persistence |
| Net delta mirroring logic | Session PnL rollups |
| `tp_sl_mirror_suspended_until_flat` flag behavior | Orderbook walk |

### 7.5 Lifecycle

```
Phase 3a:  Engine(NoOpExecutionAdapter)     → logic tests, integration test_engine_cycle
Phase 3b:  Engine(PaperExecutionAdapter)    → end-to-end paper pipeline
Phase 8:   Engine(LiveExecutionAdapter)     → real money
```

Swap is **one line** in `main.py` / app factory — no engine edits.

### 7.6 Optional enhancement (discuss)

NoOp could write to an in-memory `actions_log` list for assertions in tests instead of silent success — helps verify "engine *would have* entered" without DB trade rows.

### Tasks

- [ ] Implement `NoOpExecutionAdapter` in `execution/base.py` or `execution/noop.py` during Phase 3a
- [ ] `test_engine_cycle.py` uses NoOp; asserts FSM + position rows, not trade rows
- [ ] Document swap point in `phase3a-fsm-and-net.md` (already sketched)

---

## 8. Cross-cutting: `tp_sl_mirror_suspended_until_flat` rename

Docs say `tp_sl_mirror_suspended_until_flat`. Code still has:

| Location | Current name |
|----------|--------------|
| `src/poly_crawler/db/models/cluster_position.py` | `tp_sl_suspended` |
| `docs/reference/database-schema.md` | `tp_sl_suspended` |
| `docs/architecture.md` §2 | `tp_sl_suspended` |
| `config/schema.py` | `tp_sl_suspend_mirror_until_flat` (config key — different naming style) |

**Next session should:**

- [ ] Agree on single name: `tp_sl_mirror_suspended_until_flat` (per spec fix)
- [ ] Alembic migration: rename column
- [ ] Update ORM, docs, phase docs consistently
- [ ] Do this as part of task 2 cleanup or Phase 3a prep

---

## 9. Suggested order of work for next session

1. **Discuss** tasks 4, 5, 6, 7 in this doc — user decisions on table reduction, score GUI scope.
2. **Verify** task 2 checklist — grep phase docs for any missing spec content.
3. **Execute** task 2 — delete `spec-full.md`, fix all cross-refs, sync `tp_sl_*` naming.
4. **Execute** task 1 — update README.
5. **Optional** — split Phase 0 migration if user chooses Option B for tables.
6. **Begin Phase 1** implementation when docs are clean.

---

## 10. User decision log (fill in during next session)

| Question | Decision | Date |
|----------|----------|------|
| Keep 11 tables at Phase 0 or reduce? | **A — Keep all 11** | 2026-07-13 |
| Delete `rpc_logs` table or keep? | **Keep** | 2026-07-13 |
| Merge `clusters` into `parents`? | **No** | 2026-07-13 |
| Score tuning: CLI only or GUI in Phase 5? | **CLI Phase 2 + GUI Phase 5** | 2026-07-13 |
| Config override: file vs DB for slider changes? | **local.yaml + DB session** | 2026-07-13 |
| Proceed with `spec-full.md` deletion? | **Yes (after blocker migration)** | 2026-07-13 |

---

*Decisions locked 2026-07-13. Cleanup implementation follows on this branch.*
