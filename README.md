# Rappi Turbo — AI Purchasing Agent

An agent that **reviews purchasing recommendations, proposes a decision, executes it after human
approval, and verifies the result** — not a chatbot. Built for the Rappi "AI Buyer Agent" assignment
(Mumbai branch, INR).

> **Status:** under construction. Session A builds the deterministic core (data model, mock ERP,
> calculator, validator). See [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) for every design decision.

## How it works (short)

1. **Load facts deterministically** — stock, sales, forecast, open POs, supplier terms, budget, storage.
2. **Calculate** the right quantity with plain formulas (the LLM never does arithmetic).
3. **Decide** — an LLM reviews the facts and the baseline, and explains its verdict
   (ACCEPT / MODIFY / REJECT / INVESTIGATE, or ESCALATE).
4. **Validate** — hard constraints (budget, storage, shelf life, MOQ, case pack) can never be bypassed.
5. **Human approves**, then the system creates the PO in the ERP, **re-reads it and verifies** it.

## Repository layout

```
backend/   FastAPI service (Python 3.12, uv)
frontend/  Next.js app (later sessions)
config/    settings.yaml — business parameters (service level, tolerances, thresholds)
docs/      architecture, scenarios, evaluation (later sessions)
```

## Running locally

Full setup (Docker and no-Docker modes) arrives in a later phase. For now:

```bash
cd backend
uv sync
uv run pytest -q
```

## Configuration

Copy `.env.example` to `.env`. With no `DATABASE_URL` the backend uses a local SQLite file;
with no `REDIS_URL` it uses in-memory equivalents.
