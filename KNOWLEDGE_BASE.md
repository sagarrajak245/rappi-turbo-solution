# AI Purchasing Agent — Knowledge Base (session handoff)

> Start every new session/agent from this file. It records what was decided in the
> discovery session (2026-10-14). Nothing is implemented yet. Source brief:
> `AI Buyer Agent — Assignment.pdf` (same folder). UI reference: `dashoboard-v1.webp`.

---

## 0. How we work (user preferences)

- Scenario by scenario: **S1 fully robust first**, then S2, then S3 (S4 mostly folds into S1 constraints).
- **Discuss before coding**: problem → math → edge cases → evaluation matrix → then build.
- Production-grade but **no over-engineering**: readable files, simple > clever.
- Time budget is flexible (~12h is fine); quality > breadth.
- Every non-obvious design choice must be explainable in the interview.

## 1. What the assignment really evaluates

- "Not a chatbot — a system that **makes, executes and validates** purchasing decisions."
- Input recommendations are **not trusted** (system recs, supplier messages, forecasts can be wrong).
- **Feedback loop** (act → observe real outcome → compare to expectation → handle deviation) is the
  thing they are "particularly interested in".
- **Evaluation approach quality**: decision correct? necessary info obtained? constraints respected?
  right action? result validated? what happens when the first action fails?
- Deliverables: public GitHub repo, README (setup/run), architecture diagram, approach, test scenarios
  + evaluation approach, mock APIs/data, validation explanation, working demo, `.env.example`,
  **intact commit history**, no secrets committed.

## 2. Decisions log

| # | Decision |
|---|---|
| D1 | Backend: **Python 3.12 + FastAPI**, async throughout, **modular monolith** |
| D2 | Frontend: **Next.js (App Router) + TypeScript**, Tailwind, shadcn/ui, TanStack Query, Recharts, lucide, light Framer Motion; TS types generated from FastAPI OpenAPI (`openapi-typescript`) |
| D3 | Agent: **LangGraph**; Langfuse optional (config flag, off by default) |
| D4 | LLMs (config-swappable, keys in `.env`): decision agent **Groq `openai/gpt-oss-120b`**; reviewer agent **Groq `qwen/qwen3.8-27b`** (ID tested and working per user); **fallback for both: Gemini** (model id in config) |
| D5 | DTOs: **Pydantic v2**, separate from ORM models. ORM: **SQLAlchemy 2.0 async** + **Alembic** |
| D6 | DB by environment (only `DATABASE_URL` changes): deployed → **Supabase Postgres**; `docker-compose` → **local Postgres container**; no Docker → **SQLite file fallback** (confirmed by user; keep models/migrations portable, Alembic `render_as_batch` for SQLite). Deployed URL already has Supabase migrated + seeded via Alembic; local runs migrate + seed automatically. |
| D7 | **Redis optional**: if `REDIS_URL` set → Redis cache + **Arq** queue/worker + Redis pub/sub for notifications; else in-memory TTL cache + in-process asyncio worker + in-memory broadcaster. Same interfaces. |
| D8 | Docker: `docker-compose up` (api, worker, web, postgres, redis). **Must also run with plain local commands without Docker.** Simple bash scripts: `scripts/run_backend.sh` and `scripts/run_frontend.sh` (+ optional `scripts/run_all.sh`). Backend script auto-detects mode: Docker available → start local Postgres + Redis containers and use them; no Docker → SQLite + in-memory cache/in-process worker. Then installs deps, runs `alembic upgrade head`, seeds, starts uvicorn (+ worker when Redis). |
| D9 | Deploy: **Railway** (api, worker, web services + Redis plugin) with Supabase as DB. Railway FS is ephemeral → never rely on SQLite there. |
| D10 | Agent **only proposes**; human approves; then agent executes and validates. |
| D11 | Data model **multi-node from day one** (S2 needs it). S1 flow reviews one SKU × one node per run. |
| D12 | Mock data via deterministic seed script `seed_scenario1.py` (fixed random seed) with deliberate edge cases. No public dataset fits (none have MOQ/budget/storage); M5/Lokad optional later for S3 demand curves. |
| D13 | Currency **INR (₹, Indian grouping e.g. ₹1,25,000)**; Mumbai branch; nodes = Mumbai dark stores (Andheri-W, Bandra, Powai, Lower Parel, Thane). |
| D14 | Auth: simple email/password → JWT in httpOnly cookie. Seeded users: **Sagar — Mumbai Category Buyer** (role `buyer`), and an `admin`. Profile shows name + branch + role. Every approval records the buyer. |
| D15 | **Jev skipped** (early-access waitlist; verdict is mostly deterministic). Mention as possible future add-on. |
| D16 | Dispatch: **dict dispatch** for verdict→handler and tool registry; `match/case` only for structural matching (tool results, error types). |
| D17 | **LLM never does arithmetic.** Deterministic tools compute; LLM orchestrates, judges, explains. Deterministic validator has final say. |

## 3. Architecture

### 3.1 Layout (target)
```
backend/
  app/
    core/        config (pydantic-settings + config/settings.yaml), db, logging (run_id correlation),
                 security, cache (iface + memory/redis), queue (iface + inproc/arq), events (broadcaster)
    modules/<name>/  router.py · schemas.py (DTOs) · models.py (ORM) · repository.py · service.py
      auth, catalog, inventory, suppliers, purchasing, budget, recommendations,
      agent (graph.py, nodes/, tools/, prompts/, llm/ provider factory + fallback),
      memory, approvals, notifications, observability (llm_calls/cost), evaluation
  alembic/  scripts/seed_scenario1.py  tests/
frontend/   (Next.js)
config/settings.yaml   docs/   docker-compose.yml   .env.example   README.md
```

### 3.2 Agent graph (S1 draft, to be refined in deep dive)
```
load_context (tools) → compute (deterministic) → recall_memory → decide (LLM, structured)
 → validate (rules) → review (Qwen LLM) ──fail──► revise (≤2 attempts) ──still fail──► escalate
 → propose (persist proposal + notify) → interrupt() [human approve/modify/reject + reason]
 → execute (create PO, idempotent on proposal_id) → verify (re-read PO from system, compare to expected)
 → mismatch? → re-plan / escalate → learn (store episode; feedback → lesson)
```
- Tools (read): `get_recommendation, get_inventory, get_sales_history, get_demand_forecast,
  get_open_pos, get_supplier_terms, get_budget, get_storage_capacity`.
  Tools (compute): `calc_inventory_position, calc_net_need, apply_constraints, project_stock(days)`.
  Actions (gated): `create_po`, later `modify_po`, `cancel_po`.
- Mock purchasing/supplier API can return **surprises** (partial ack, price change, rejection) to
  exercise the feedback loop.

### 3.3 Reliability
- **Idempotency**: `Idempotency-Key` header on `POST /runs`; proposals unique `(run_id, action_hash)`;
  PO creation unique on `proposal_id` (double-approve → one PO).
- **Recovery**: LangGraph checkpointer (Postgres saver; SQLite saver in fallback mode) keyed by
  `thread_id = run_id`; on worker startup resume runs stuck in `running`.
- **Retries**: bounded (config), LLM provider fallback Groq → Gemini, structured-output validation
  with Pydantic; on invalid output retry then escalate.
- Run status machine: `queued → running → awaiting_approval → executing → verifying →
  completed | escalated | failed`.

### 3.4 Memory & learning
- Short-term: LangGraph state (per run).
- Episodic: past runs (decision, outcome, human feedback) retrieved by SKU / node / supplier / category.
- Persistent: **lessons** distilled by LLM from feedback (e.g. "Andheri dairy: +10% on weekends"),
  scoped by keys, toggleable, `times_applied` counter, cited in explanations.
- **Rule: lessons may change soft choices but never override hard constraints.** No vector DB.

### 3.5 Observability & cost
- Own `llm_calls` table (run_id, node, provider, model, tokens in/out, latency, cost via config price
  table, fallback_used). Admin dashboard reads it — works with Langfuse off.
- Structured JSON logs with run_id.

### 3.6 Notifications
- `notifications` table + **SSE** stream; Redis pub/sub when available.
- Events: awaiting approval, PO created & validated, validation mismatch, escalated, run failed/retrying.

### 3.7 Known gotchas
- LangChain `ChatGroq.with_structured_output()` failed for gpt-oss (unsupported `strict` param,
  langchain issue #34155). **Test in hour 1**; fallback = JSON-object mode + Pydantic validation.
- Supabase **transaction pooler (6543) breaks asyncpg** prepared statements → use session pooler/direct
  connection or `statement_cache_size=0`; Alembic uses direct URL (`DATABASE_URL` + `DATABASE_URL_DIRECT`).
- Railway FS ephemeral; keep secrets only in `.env` (never commit).

## 4. Data model (initial)
`users(name, email, role, branch)`, `nodes`, `products(sku, name, category, perishable,
shelf_life_days, unit_volume)`, `suppliers(active, reliability)`, `supplier_products(unit_cost_inr,
moq, case_pack, lead_time_days, active)`, `inventory_snapshots(node, sku, on_hand, as_of)`,
`sales_history(node, sku, date, qty)`, `demand_forecasts(node, sku, date, qty)`,
`purchase_orders` + `po_lines(status, eta, qty_ordered, qty_confirmed, qty_received)`,
`budgets(node|category, period, amount, committed)`, `storage_capacity(node, zone/category, capacity)`,
`recommendations(sku, node, qty, source, created_at)`, `agent_runs(scenario, status, idempotency_key,
thread_id, attempts, error)`, `tool_calls` (audit), `proposals(run_id, action_type, payload,
action_hash, status)`, `approvals(proposal_id, user_id, decision, modified_qty, reason, reason_tags)`,
`lessons(scope keys, text, active, source_approval_id, times_applied)`, `llm_calls`,
`notifications(user_id, type, payload, read_at)`, `eval_runs`, `eval_results`.

## 5. Frontend scope & design system

**Design (from dashoboard-v1.webp, enhanced):** warm cream bg with soft yellow radial glow; frosted
white cards, radius ~24px, soft shadow; accent yellow ~`#F5D547`; dark cards `#1F1F1F` for the
"needs your decision" list; pill nav with black active pill; big thin numerals for KPIs; striped
progress bars (budget/storage). Verdict colors: ACCEPT green · MODIFY yellow · REJECT coral (Rappi
`#FF441F`-ish) · INVESTIGATE slate. Audience = purchasing manager → plain language, no jargon.

**Pages:**
1. **Home** — "Good morning, Sagar · Mumbai Category Buyer"; KPI strip (pending approvals,
   ₹ committed today, agent agreement %, budget/storage bars); 3 scenario cards (S2/S3 "soon" until
   built); dark "Needs your decision" list; recent agent activity timeline.
2. **Recommendations inbox (S1)** — rows: product, node, recommended→agent qty, verdict badge,
   status, one-line reason; filters; "Run agent" per row / all.
3. **Review page (core)** — "In short" sentence; **14-day stock projection chart** (no order / system
   800 / agent qty, stockout day, storage ceiling); facts panel (each fact links to its tool call);
   constraint chips; collapsible "How the agent decided" trace; Approve / Change qty / Reject with a
   **confirm modal showing the exact PO**; feedback reason chips + free text; post-approval result
   panel (PO created → re-read → ✔ matches / ⚠ differs + what agent did).
4. **Purchase orders** — agent-created POs with validation status, link to run.
5. **Learned memory** — lessons, source feedback, times applied, on/off toggle.
6. **Admin technical dashboard** (admin only) — cost ₹/$ by day/model/node, tokens, runs over time
   (success/escalated/retried/failed), latency per graph node, fallback usage, top validator failures,
   reviewer disagreement rate, eval scores, Langfuse trace links.
7. **Evaluation** — scenario × check pass/fail matrix.
- **Notifications**: bell with unread count + dropdown, toasts, click → run page (SSE).

## 6. Docs deliverables (`docs/`)
`architecture.md` (Mermaid diagram + plain-language walkthrough), `scenario-1.md` / `-2` / `-3`
(problem, data used, decision logic, flow diagram, edge cases, examples), `evaluation.md`,
`decisions.md` (ADR-style, from §2), `deployment.md`. Written so a non-engineer teammate understands.

## 7. Scenario 1 starter (input for the deep-dive discussion — NOT final)

**Problem:** system recommends **800 units**; agent decides ACCEPT / MODIFY / REJECT / INVESTIGATE
and explains why, using inventory, demand, open POs, lead time, MOQ, budget, storage.

**Draft math (deterministic):**
- `D` avg daily demand (forecast), `σ` daily std dev; protection period `P = lead_time + review_period`
- safety stock `SS = z·σ·√P` (`z` from service level in config, e.g. 95% → 1.65)
- usable inbound = open PO qty with ETA ≤ today + P **and not overdue**
- inventory position `IP = on_hand + usable_inbound − committed`
- target `T = D·P + SS`; net need `N = max(0, T − IP)`
- round: `max(MOQ, ceil(N / case_pack) · case_pack)` (only if N > 0)
- caps: storage (projected stock at arrival + qty ≤ free capacity), budget (`qty·unit_cost ≤ remaining`),
  perishables `qty ≤ D · shelf_life_days`
- verdict draft: N = 0 → REJECT; |agent − 800| ≤ tolerance (config, e.g. 10%) → ACCEPT; feasible
  different qty → MODIFY; bad/stale/contradictory data or unresolvable constraint conflict → INVESTIGATE/escalate.

**Edge-case seeds (each becomes a seeded SKU×node + eval case):**
E1 rec correct → accept · E2 open PO already covers → reject · E3 over-recommend (ignored open PO) →
modify down · E4 under-recommend → modify up · E5 need < MOQ · E6 case-pack rounding · E7 budget
insufficient · E8 storage insufficient · E9 MOQ > storage/budget (conflict) → escalate · E10 overdue
open PO (don't count) · E11 stale inventory snapshot · E12 missing/negative inventory or forecast ·
E13 perishable shelf-life cap · E14 supplier inactive · E15 duplicate run request · E16 double approve
→ one PO · E17 LLM invalid output / constraint-violating qty → validator → revise · E18 Groq down →
Gemini · E19 worker crash mid-run → resume · E20 execution mismatch (mock returns different qty/price)
→ verify catches → handle · E21 human modify + reason → lesson → applied next run · E22 untrusted
free-text fields (e.g. supplier note) treated as data, not instructions.

**Evaluation matrix columns (draft):** verdict correct · qty within expected band · required tools
called · constraints respected · correct action (proposal / none / escalation) · validation performed ·
recovery behaviour · explanation grounded (numbers match facts). Run each case N=3 for LLM
non-determinism; deterministic checks first, LLM-as-judge optional. CLI `python -m app.evaluation run
--scenario 1` + results shown in UI.

**Open questions for the deep dive:** review period length; who "owns" the verdict (deterministic
baseline vs LLM override with justification); tolerance %; investigate vs escalate distinction;
partial coverage when budget-capped (buy what fits + escalate?); expected mock-ERP surprises for E20;
lesson extraction approval (auto vs buyer confirms).

## 8. Later scenarios (notes)
- **S2** (500 ordered, supplier confirms 250): recompute coverage with 250; options = accept partial,
  backorder, alternate supplier PO for shortfall, inter-node transfer (multi-node), escalate; update
  original PO to confirmed qty. Needs `seed_scenario2.py`, alternate suppliers, supplier reliability.
- **S3** (demand spike): evidence check (trend vs one-off spike, promo, stockout-censored sales);
  days of cover vs PO ETA; options = increase/expedite PO, extra PO, watch. Optional M5-derived curves.

## 9. Next session prompt
"Read `KNOWLEDGE_BASE.md`. We are starting **Scenario 1**. No code yet: deep-dive the problem, finalize
the math and decision rules, answer the §7 open questions, finalize edge cases and the evaluation
matrix, then propose the implementation plan (Plan Mode) for S1 + the shared foundation."
