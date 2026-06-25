# API Routes

**Source:** docs/architecture.md §10

---

FastAPI endpoints planned for v0.1.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/alerts` | List alerts with filters |
| PATCH | `/api/alerts/{id}/false-positive` | Toggle false-positive label |
| GET | `/api/positions` | List cluster positions |
| GET | `/api/positions/{id}` | Position detail + trade history |
| POST | `/api/positions/{id}/review` | Approve/reject SIGNAL state |
| GET | `/api/sessions` | List sessions |
| POST | `/api/sessions` | Create new session |
| PATCH | `/api/sessions/{id}` | Update session (name, private, include) |
| GET | `/api/config` | Get current config (redacted secrets) |

All routes behind FastAPI. Implementation in `src/poly_crawler/api/`.
