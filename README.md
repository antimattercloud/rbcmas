# RBCMAS — Research Building Chemical Management & Accountability System

**Created by Ditij M. Dhameliya**
Developed by DM. Dhameliya

A real, working institutional web application for managing chemical inventory across the laboratories of a research building — chemical inventory, container-level tracking, usage accountability, physical/digital reconciliation, transfers, procurement, analytics, CSV data control, and a full audit trail.

This is **not** an SDS/waste/QR/EHS system by design (see [Scope](#scope)). It focuses on: **Chemical Inventory + Usage + Accountability + Reconciliation + Analytics + Procurement.**

---

## 1. Quick start (Windows, local, SQLite)

```bash
cd rbcmas
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.seed
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and sign in with one of the demo accounts (password `demo1234`):

| Role | Email |
|---|---|
| Administrator | admin@rbcmas.local |
| Laboratory Manager | labmanager@rbcmas.local |
| Researcher | researcher@rbcmas.local |
| Auditor | auditor@rbcmas.local |

All demo data (chemicals, containers, labs, users, transactions) is clearly tagged `DEMO DATA` / `DEMO` badges in the UI. Delete `data/rbcmas.db` and re-run `python -m app.seed` to reset it back to the demo dataset.

Linux/Mac: same commands, using `source .venv/bin/activate` instead of the Windows activate script.

### Removing all demo data (going live)

When you're ready to stop using the demo dataset and enter your own real inventory, **don't just delete the demo users** — that would delete every account and lock you out. Instead:

```bash
python scripts/remove_demo_data.py --admin-name "Your Name" --admin-email you@yourlab.org --admin-password "a-strong-password"
```

This creates (or promotes, if it already exists) a real, non-demo Administrator account with the credentials you give it, then removes every chemical, container, laboratory, location, demo user account, and their ledger/transfer/audit history — leaving the app empty and ready for `Chemicals > Add Chemical`, `Laboratories > Add Laboratory`, CSV import, etc. Pass `--keep-users` if you want to keep the demo user accounts (e.g. to keep testing role permissions) and only clear out the inventory data.

The script also refuses to orphan real data: if a non-demo container is already pointing at a demo chemical or demo laboratory (e.g. you added your own container against a demo chemical before running this), that chemical/laboratory is kept instead of deleted, and the script tells you so.

## 2. Architecture

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11+, FastAPI | Fast, async-capable, typed, free |
| ORM / DB | SQLAlchemy 2.0 + Alembic | Same models run on SQLite (default) or PostgreSQL |
| Database | SQLite (`data/rbcmas.db`) by default; PostgreSQL via `DATABASE_URL` | Zero-install local use; scales to a real server later |
| Frontend | Server-rendered Jinja2 + hand-written CSS + **vanilla JS only** | No React/Vue/build step/CDN dependency — fast, offline-capable, matches the "extremely lightweight" requirement |
| Charts | Hand-generated inline SVG | No charting library, no external asset |
| Auth | Signed session cookie (`itsdangerous`) + bcrypt password hashing | Simple, no JWT complexity needed for a LAN app |
| CSV/Excel | stdlib `csv` + `openpyxl` | No pandas dependency, fast startup |
| PDF reports | Browser print-to-PDF on report pages | Zero extra dependency; a real PDF generator (e.g. reportlab) is a documented future addition |

Everything runs **fully offline** after install — no third-party API, no mandatory cloud service, no subscription.

### The signature feature: the ledger

Every quantity change on a container is one row in the append-only `inventory_transactions` table (`RECEIVE, OPEN, USE, TRANSFER_OUT, TRANSFER_IN, ADJUSTMENT, RETURN, PHYSICAL_COUNT`). Nothing ever silently overwrites `container.expected_quantity` — it is always the sum of this ledger. Physical verification records a zero-delta `PHYSICAL_COUNT` checkpoint; if the variance exceeds the configured tolerance, a `reason` is mandatory and a pending `InventoryAdjustment` is created, which only changes the expected quantity once a Lab Manager/Admin approves it (a real `ADJUSTMENT` ledger row). See `app/services/inventory_service.py`.

### Data model

See `app/models/` — `users`, `laboratories`, `locations` (self-referential Building→Floor→Laboratory→Room→Storage Unit→Cabinet→Shelf tree), `chemicals` + `chemical_aliases` + `suppliers`, `containers`, `inventory_transactions`, `transfer_records`, `physical_counts`, `inventory_adjustments`, `purchase_requests`, `projects`/`experiments`, `audit_logs`, `import_audits`, `system_settings`.

## 3. Roles

Four fixed roles (no dynamic permission engine, per spec): **Administrator**, **Laboratory Manager**, **Researcher**, **Auditor** (read-only). Enforced via FastAPI dependencies in `app/security.py` (`require_admin`, `require_manager_or_admin`, `require_write`, `require_user`). No Safety Officer role exists, by design.

Admins can create users directly from Administration > Users. People can also self-register from a "Create an account" link on the login page (`/register`); self-registered accounts are created as **Researcher** and **inactive** — an administrator must approve them (the same Enable/Disable toggle on Administration > Users) before they can sign in. This keeps role/laboratory assignment a deliberate admin decision while still letting staff request access without an admin manually typing in their details first.

## 4. What's implemented (V1 + core of V2)

- Authentication, RBAC, branded UI, sidebar navigation, professional footer on every page.
- Chemical Master (with synonyms/CAS/grade/thresholds) separated from physical Containers (one chemical → many containers).
- Chemical Passport page with tabs: Identity / Inventory / Usage History / Transfers / Physical Verification / Audit History.
- Laboratory & Location management (full hierarchy), Laboratory drill-down view.
- Manual data entry for every entity, with validation and duplicate detection.
- CSV import/export for Laboratories, Locations, Chemicals, Containers: download template → upload → **validate → preview (counts + row-level error table) → confirm → import**, add-or-update semantics, duplicate protection, import audit trail. Quantities are **never** touched by CSV update — only the ledger controls quantity.
- Usage tracking → inventory ledger → balance sheet (Opening + Received + Transfer In − Used − Transfer Out + Adjustment = Expected Closing) compared against the last physical count.
- Physical vs. digital reconciliation with mandatory reason + admin/manager approval workflow for discrepancies beyond tolerance ("INVENTORY DISCREPANCY — REVIEW REQUIRED").
- Inter-lab transfers: whole-container move or automatic split into a new container when a partial quantity is transferred; can never exceed available stock.
- Expiry management (configurable thresholds), low-stock detection (chemical-level, aggregated across containers), dead-stock/inactive-stock detection (configurable window).
- Procurement: system-suggested purchase quantity (3-month moving average + safety stock − current/pending stock, clearly labelled as an estimate) with a full human approval → ordered → received workflow. No automatic purchasing.
- Dashboard, Analytics (consumption trend, most-consumed chemicals, lab-wise inventory, per-chemical average consumption), 11 Reports (Inventory, Consumption, Reconciliation, Expiry, Low Stock, Transfer, Procurement, Laboratory-wise, Chemical Annual, Audit, Dead Stock) exportable to CSV/XLSX/print-to-PDF.
- Smart search: deterministic rule-based parsing for patterns like "where is X", "chemicals in Lab X", "expiring this month/within N days", "below N mL", "unused for N months/years", "who used X" — falls back to indexed keyword search. No external AI calls.
- Full audit log (append-only, viewable/filterable/exportable), CSV import audit trail.
- Backup/restore script for SQLite (`scripts/backup.py`); admin-configurable thresholds (expiry warnings, dead-stock window, variance tolerance) actually take effect at runtime (`system_settings` table, checked by the services layer).

### Deliberately deferred (documented, not built this pass)

- True statistical demand forecasting beyond the 3-month moving average (weighted MA / exponential smoothing).
- Natural-language search beyond the rule-based pattern set.
- A dedicated PDF report generator (reportlab) — the browser's print-to-PDF covers this need today.
- Visual building/floor map.

These are natural next steps and the codebase (ledger, services, REPORT_FUNCS registry) is structured so they can be added without touching the core.

## 5. Performance

Tested with `scripts/perf_seed.py` at **~12,000 containers** (base demo data + bulk-inserted synthetic containers) on a single laptop-class machine:

| Page | Response time |
|---|---|
| Dashboard | ~0.2–0.5s |
| Containers list (paginated, filtered) | ~40–100ms |
| Smart search | ~60–100ms |
| Analytics | ~0.2–0.3s |
| Full inventory report (all rows) | ~1.1–1.4s |

All interactive pages stay well under the ~2s/~500ms targets. Bulk report generation over the full dataset (not just what's shown on screen) takes a little over a second at this scale — on-screen report tables are capped at 500 rows with a note to use Export for the complete data, per the "never dump thousands of rows in a browser table" requirement. Search, dashboard, and list pages always use server-side pagination and indexed queries; the full chemical/container database is never sent to the browser.

To test at a larger scale yourself:

```bash
python -m app.seed              # base reference data (run once)
python scripts/perf_seed.py --containers 50000
```

## 6. Running on PostgreSQL

```bash
# .env
DATABASE_URL=postgresql+psycopg2://rbcmas_user:changeme@localhost:5432/rbcmas
```

Install the driver (`pip install psycopg2-binary`), then run the same `python -m app.seed` and `uvicorn` commands. All models avoid dialect-specific types so they work unchanged. Note: the Chemical-wise Annual Report currently uses SQLite's `strftime` for year extraction — on PostgreSQL, swap it for `extract('year', ...)` in `app/services/reports_service.py::chemical_annual_report`.

## 7. Backup & restore (SQLite)

```bash
python scripts/backup.py backup
python scripts/backup.py restore backups/rbcmas_2026-09-22_101500.db
```

For PostgreSQL, use `pg_dump` / `pg_restore` instead.

## 8. Tests

```bash
pytest
```

25 tests cover: ledger arithmetic and balance-sheet reconciliation, the discrepancy/approval workflow (including that a rejected adjustment never changes quantity), whole vs. partial (splitting) transfers and their guardrails, CSV import (create/update/duplicate/error handling, and that CSV never silently touches quantity history), and role-based access control across all four roles.

## 9. Project layout

```
app/
  main.py            FastAPI app, middleware, friendly error pages
  config.py           Settings (.env)
  database.py          Engine/session
  security.py           Auth, sessions, RBAC dependencies
  render.py               Jinja2 render helper (flash messages, settings, pagination query-string helper)
  charts.py                 Hand-rolled inline SVG chart helpers
  models/                    SQLAlchemy models
  services/                    Business logic: inventory_service (the ledger), transfer_service,
                                csv_service, search_service, analytics_service, reports_service,
                                audit_service, export_service, settings_service, codes
  routers/                      One router per module (chemicals, containers, usage, verification,
                                 transfers, procurement, analytics, reports, audit, data_io, admin, ...)
  templates/                     Jinja2 pages
  static/                         CSS + vanilla JS, no external assets
  seed.py                          Demo data (clearly tagged DEMO DATA)
alembic/                            Migrations
scripts/                             backup.py, perf_seed.py
tests/                                pytest suite
```

## 10. Data ownership

You can Add, View, Edit, Import (CSV), Export (CSV/XLSX), and Back up your own data at any time — nothing is locked into a proprietary format or external platform. The SQLite file (or your own PostgreSQL database) is yours.

## Scope

By design, this system does **not** include: SDS management, waste disposal workflows, QR-code scanning/labels, or a Safety Officer role. It is an inventory, usage, accountability, reconciliation, analytics, and procurement system — not a full EHS platform.
