# Alerts

**Source:** spec.md §11

---

## Alert types

Stored in `alerts.alert_type`:

| Type | When |
|------|------|
| `fund` | Parent funds a known account |
| `birth` | New Polymarket account detected under a flagged parent |
| `sibling` | New sibling relationship discovered |
| `conflict` | Two+ siblings hold opposing sides of the same market |
| `conflict_resolved` | Opposing overlap ended |
| `signal` | Entry rules passed, position in SIGNAL state |
| `entry` | Position entered IN_POSITION |
| `exit` | Position closed |

## Channels

v0.1: **Dashboard** only. Schema reserves space for future Telegram / Discord / webhooks.

## False positives

Alerts can be labeled `is_false_positive: true` via the dashboard for tuning signal quality.
