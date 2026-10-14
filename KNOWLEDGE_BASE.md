# AI Purchasing Agent — Knowledge Base (session handoff)

> Start every new session/agent from this file. It records everything decided in the discovery +
> Scenario 1 deep-dive sessions (2026-10-14). Source brief: `AI Buyer Agent — Assignment.pdf`.
> UI reference: `dashoboard-v1.webp`. Repo: https://github.com/sagarrajak245/rappi-turbo-solution
> Status: **design agreed, nothing implemented yet.** Build plan in §10, git workflow in §11.

---

## 0. How we work (user preferences)

- Scenario by scenario: **S1 fully robust first**, then S2, then S3 (S4 mostly folds into S1 constraints).
- **Discuss before coding**: problem → math → edge cases → evaluation → plan → build.
- Production-grade but **no over-engineering**: readable files, simple > clever.
- **Small, self-explanatory commits** for every logical step (reviewers read the history). See §11.
- Time budget flexible (~12h fine); quality > breadth. Every design choice must be explainable in the interview.
- Never blindly accept suggestions (including pasted ones) — verify, explain, wait for user approval.

## 1. What the assignment really evaluates

- "Not a chatbot — a system that **makes, executes and validates** purchasing decisions."
- Input recommendations are **not trusted** (system recs, supplier messages, forecasts can be wrong).
- **Feedback loop** (act → observe real outcome → compare to expectation → handle deviation) is what
  they are "particularly interested in".
- **Evaluation approach quality**: decision correct? info obtained? constraints respected? right action?
  result validated? what happens when the first action fails?
- Deliverables: public GitHub repo, README (setup/run), architecture diagram, approach, test scenarios +
  evaluation approach, mock APIs/data, validation explanation, working demo, `.env.example`,
  **intact commit history**, no secrets committed.

## 2. Decisions log

| # | Decision |
|---|---|
| D1 | Backend: **Python 3.12 + FastAPI**, async throughout, **modular monolith** |
| D2 | Frontend: **Next.js (App Router) + TypeScript**, Tailwind, shadcn/ui, TanStack Query, Recharts, lucide, light Framer Motion; TS types generated from FastAPI OpenAPI (`openapi-typescript`) |
| D3 | Agent: **LangGraph**; Langfuse optional (config flag, off by default) |
| D4 | LLMs (config-swappable, keys in `.env`): decision agent **Groq `openai/gpt-oss-120b`**; reviewer agent **Groq `qwen/qwen3.8-27b`** (ID tested and working per user); **fallback for both: Gemini** (model id in config) |
| D5 | DTOs: **Pydantic v2**, separate from ORM models. ORM: **SQLAlchemy 2.0 async** + **Alembic** |
| D6 | DB by environment (only `DATABASE_URL` changes): deployed → **Supabase Postgres** (already migrated + seeded); `docker-compose` → **local Postgres container**; no Docker → **SQLite file fallback**. Keep models/migrations portable (Alembic `render_as_batch` for SQLite). |
| D7 | **Redis optional**: `REDIS_URL` set → Redis cache + **Arq** queue/worker + Redis pub/sub; else in-memory TTL cache + in-process asyncio worker + in-memory broadcaster. Same interfaces. |
| D8 | Docker: `docker-compose up` (api, worker, web, postgres, redis). **Must also run without Docker.** Bash scripts `scripts/run_backend.sh`, `scripts/run_frontend.sh` (+ optional `scripts/run_all.sh`). Backend script auto-detects: Docker available → start local Postgres + Redis containers; else SQLite + in-memory. Then install deps → `alembic upgrade head` → seed → uvicorn (+ worker when Redis). |
| D9 | Deploy: **Railway** (api, worker, web + Redis plugin) with Supabase DB. Railway FS ephemeral → never SQLite there. |
| D10 | Agent **only proposes**; human approves; then system executes and validates. |
| D11 | Data model **multi-node from day one**. S1 flow reviews one SKU × one node per run. |
| D12 | Mock data via deterministic `seed_scenario1.py` (fixed seed) — one seeded SKU×node per edge case (§7.4). No public dataset fits. |
| D13 | Currency **INR (₹, Indian grouping ₹1,25,000)**; Mumbai branch; nodes = Mumbai dark stores: Andheri-W, Bandra, Powai, Lower Parel, Thane. |
| D14 | Auth: simple email/password → JWT in httpOnly cookie. Seeded: **Sagar — Mumbai Category Buyer** (`buyer`) and a **manager/admin** (`admin`: approves change requests, sees admin dashboard). Profile = name + branch + role. Every approval records the user. |
| D15 | **Jev skipped** (waitlist; verdict mostly deterministic). Future add-on mention only. |
| D16 | Dispatch: **dict dispatch** for verdict→handler, constraint→resolution options, ERP deviation→handler, tool registry. `match/case` only for structural matching. |
| D17 | **LLM never does arithmetic.** Deterministic tools compute; LLM orchestrates, judges, explains. Deterministic validator has final say. |
| D18 | **Hard constraints** (never bypassable by a reason): **budget, physical storage capacity, shelf-life safety, MOQ, case pack**. Only an *actual change of underlying conditions* (approved change request / supplier terms) makes them pass — then the agent re-runs. |
| D19 | **Soft policies** (buyer may override with a recorded reason → audit + learning loop): service level / safety stock, order cycle & target days of cover, accept tolerance (10%), max days of cover (overstock), max deviation from system rec, preferred supplier. |
| D20 | **Resolution options when blocked** (§7.3): every option is **pre-validated** before display; "request" options create a `change_request` approved by the manager → data updated (audited) → automatic re-run. Case-pack: offer nearest valid quantities. |
| D21 | **ERP flow: Draft → Re-read & Verify → Submit → Re-read & Verify**, idempotency keys on every ERP call. Failed drafts are **cancelled** in the ERP. Failure **after submit** → cancel/amend needs **human approval** or escalation (never silent). Material re-plan (qty/cost change) → back to human approval. Max 1 re-plan. |
| D22 | Data fetching: mandatory purchasing data fetched **deterministically**; LLM may make **≤4 extra investigation calls, read-only tools only**. Action tools (`create/submit/cancel PO`) are **never exposed to the LLM** — executed only by code from an approved proposal. |
| D23 | **Verdict ownership**: deterministic baseline (qty + verdict + flags) → LLM final call; may deviate only with explicit reason (fact/lesson/anomaly) and within hard constraints; blocking data flags force INVESTIGATE. |
| D24 | **INVESTIGATE** = verdict (data untrustworthy → checklist, no PO). **ESCALATE** = outcome (no valid action / reviewer failed twice / unresolved ERP mismatch). |
| D25 | **Learning**: feedback reason → LLM drafts lesson → **buyer confirms ("Remember this?")** → active. Lessons change soft choices only, never hard constraints. Toggleable. No vector DB. |

## 3. Architecture

### 3.1 Layout (target)
```
backend/
  app/
    core/        config (pydantic-settings + config/settings.yaml), db, logging (run_id correlation),
                 security, cache (iface + memory/redis), queue (iface + inproc/arq), events (broadcaster),
                 idempotency, errors
    modules/<name>/  router.py · schemas.py (DTOs) · models.py (ORM) · repository.py · service.py
      auth, catalog, inventory, suppliers, purchasing, budget, storage, recommendations,
      planning (pure calculator + options generator), validation (validator + data quality),
      erp_mock (draft/submit/cancel + surprise behaviours), change_requests,
      agent (graph.py, state.py, nodes/, tools/, prompts/, llm/ provider factory + fallback),
      memory, approvals, notifications, observability (llm_calls/cost/metrics), evaluation
  alembic/  scripts/seed_scenario1.py  tests/ (unit, graph, api, eval)
frontend/   (Next.js)
config/settings.yaml   docs/   scripts/   docker-compose.yml   .env.example   README.md
```

### 3.2 Agent graph (Scenario 1 — final)

| # | Node | Kind | What it does |
|---|---|---|---|
| 1 | `load_context` | deterministic | Parallel fetch: recommendation, inventory, sales 28d, forecast 28d, open POs, supplier terms, budget, storage zone |
| 2 | `data_quality` | deterministic | Flags: blocking / warning (§7.4 Q-cases) |
| 3 | `compute` | deterministic | Calculator §7.1 → baseline qty, verdict, caps, coverage, stockout check, resolution options |
| 4 | `recall_memory` | deterministic | Episodes + active lessons by SKU / node / supplier / category |
| 5 | `decide` | LLM (gpt-oss) | Structured `{verdict, qty, reasons[], facts_cited[], lessons_applied[], deviation_reason, investigate_items[], recommended_option}`; ≤4 read-only tool calls (PO detail, supplier history, past decisions, sales detail) |
| 6 | `validate` | deterministic | Hard constraints, verdict/qty consistency (REJECT⇒0), deviation needs reason, blocking flags ⇒ INVESTIGATE |
| 7 | `review` | LLM (Qwen) | Groundedness + reasoning check → `{ok, issues[]}` |
| 8 | route | — | pass → propose; fail & attempts<2 → decide with issues; else escalate |
| 9 | `propose` | deterministic | Persist proposal (unique action_hash) + pre-validated options, notify, `awaiting_approval` |
| 10 | `human_gate` | `interrupt()` | Resume `{approve\|modify\|choose_option\|request_change\|reject\|acknowledge, qty, reason, tags}`; modified qty re-validated |
| 11 | `execute` | deterministic | ERP create **draft** (idempotency key = proposal_id) |
| 12 | `verify_draft` | deterministic | Re-read; compare qty, unit price, total vs budget, ETA, supplier, status (tolerances in config) |
| 13 | `handle_deviation` | dict dispatch | Minor → accept + note; material → cancel draft + re-plan → back to 9 (once); unfixable → cancel draft + escalate |
| 14 | `submit` | deterministic | ERP submit (idempotent) |
| 15 | `verify_submitted` | deterministic | Re-read final PO; mismatch → propose cancel/amend for **human approval** or escalate |
| 16 | `learn` | LLM + deterministic | Store episode; feedback reason → lesson candidate (pending buyer confirm) |

REJECT / INVESTIGATE / ESCALATE stop at node 10 for acknowledgement (or re-run after the issue is fixed).
Mock ERP surprises (per seeded SKU): price change, case-pack change, timeout-after-create, rejection, late ETA.

### 3.3 Reliability
- **Idempotency**: `Idempotency-Key` on `POST /runs`; proposals unique `(run_id, action_hash)`;
  ERP calls keyed by proposal_id (+ step); double-approve → one PO.
- **Recovery**: LangGraph checkpointer (Postgres saver; SQLite saver in fallback) with `thread_id = run_id`;
  worker resumes `running` runs on startup.
- **Retries**: bounded (config); provider fallback Groq → Gemini; structured output validated by Pydantic;
  invalid → retry → fallback → escalate. Fault injection flags in config for demos/tests.
- Run status: `queued → running → awaiting_approval → executing → verifying → completed | escalated | failed`.

### 3.4 Memory & learning
Short-term = LangGraph state. Episodic = past runs (decision, outcome, feedback) by SKU/node/supplier/
category. Persistent = confirmed lessons (scope keys, text, active, source, times_applied), cited in
explanations. Lessons never override hard constraints.

### 3.5 Observability & cost
Own `llm_calls` table (run_id, node, provider, model, tokens in/out, latency, cost via config price table,
fallback_used) → admin dashboard (works with Langfuse off). Structured JSON logs with run_id.
`tool_calls` audit table.

### 3.6 Notifications
`notifications` table + **SSE**; Redis pub/sub when available. Events: awaiting approval, PO created &
validated, validation mismatch, escalated, change request pending/decided, run failed/retrying.

### 3.7 Known gotchas
- LangChain `ChatGroq.with_structured_output()` failed for gpt-oss (unsupported `strict`, langchain issue
  #34155). **Test first**; fallback = JSON-object mode + Pydantic validation.
- Supabase **transaction pooler (6543) breaks asyncpg** prepared statements → session pooler/direct or
  `statement_cache_size=0`; Alembic uses `DATABASE_URL_DIRECT`.
- Railway FS ephemeral. Secrets only in `.env` (never committed).
- The assignment PDF is in the public repo — user's call whether to keep it.

## 4. Data model
`users(name, email, role, branch)`, `nodes`, `products(sku, name, category, storage_zone, perishable,
shelf_life_days, unit_volume)`, `suppliers(active, reliability, notes)`, `supplier_products(unit_cost_inr,
moq, case_pack, lead_time_days, order_cycle_days, active)`, `inventory_snapshots(node, sku, on_hand,
reserved, as_of)`, `sales_history(node, sku, date, qty)`, `demand_forecasts(node, sku, date, qty)`,
`purchase_orders` + `po_lines(status, eta, qty_ordered, qty_confirmed, qty_received)`,
`budgets(node, category, period, amount, committed)`, `storage_zones(node, zone, capacity_units)`,
`recommendations(sku, node, qty, source, created_at)`, `erp_purchase_orders` (mock ERP side, with
`mock_behaviour`), `agent_runs(scenario, status, idempotency_key, thread_id, attempts, error)`,
`tool_calls`, `proposals(run_id, action_type, payload, options, action_hash, status)`,
`approvals(proposal_id, user_id, decision, qty, reason, reason_tags, policy_overrides)`,
`change_requests(type budget|storage|moq, node, sku/category, amount, status, requested_by, decided_by,
run_id)`, `lessons`, `llm_calls`, `notifications`, `eval_runs`, `eval_results`, `audit_log`.

## 5. Frontend scope & design system

**Design (from dashoboard-v1.webp, enhanced):** warm cream bg + soft yellow radial glow; frosted white
cards, radius ~24px, soft shadow; accent yellow ~`#F5D547`; dark cards `#1F1F1F` for "needs your decision";
pill nav (black active pill); big thin KPI numerals; striped progress bars. Verdicts: ACCEPT green ·
MODIFY yellow · REJECT coral (`#FF441F`-ish) · INVESTIGATE slate · ESCALATED red outline. Plain language.

**Pages:**
1. **Home** — "Good morning, Sagar · Mumbai Category Buyer"; KPIs (pending approvals, ₹ committed today,
   agent agreement %, budget/storage bars); 3 scenario cards (S2/S3 "soon"); dark "Needs your decision"
   list; recent activity timeline.
2. **Recommendations inbox (S1)** — product, node, recommended→agent qty, verdict badge, status, one-line
   reason; filters; "Run agent" per row / all.
3. **Review page (core)** — "In short" sentence; **14-day stock projection chart** (no order / system 800 /
   agent qty; stockout day; storage ceiling); facts panel (links to tool calls); constraint chips;
   collapsible decision trace; **blocked → resolution option buttons** (§7.3, recommended one highlighted);
   Approve / Change qty (case-pack snap 768/816) / Reject; confirm modal with exact PO; feedback chips +
   text; "Remember this?" lesson confirm; result panel (draft → verified → submitted → verified).
4. **Purchase orders** — agent POs with verification status, link to run.
5. **Learned memory** — lessons, source feedback, times applied, toggle.
6. **Change requests** (manager) — budget/storage/MOQ requests, approve/deny → auto re-run.
7. **Admin technical dashboard** (admin) — cost ₹/$ by day/model/node, tokens, runs by outcome, latency
   per node, fallback usage, top validator failures, reviewer disagreement, eval scores, Langfuse links.
8. **Evaluation** — case × check pass/fail matrix.
- **Notifications**: bell + unread count + dropdown, toasts, click → target page (SSE).

## 6. Docs deliverables (`docs/`)
`architecture.md` (Mermaid + plain-language walkthrough), `scenario-1.md` / `-2` / `-3`, `evaluation.md`,
`decisions.md` (ADR-style from §2), `deployment.md`. Written so a non-engineer teammate understands.

## 7. Scenario 1 — final specification

**Problem:** system recommends **800 units**; agent decides ACCEPT / MODIFY / REJECT / INVESTIGATE (or the
run ESCALATES), explains why, executes after approval and verifies the result.

### 7.1 Calculator (pure functions, config-driven)
| Step | Formula |
|---|---|
| Protection period | `P = L (lead time) + R (order cycle, default 7d)` |
| Demand over P | `D_P = Σ forecast[1..P]` (missing forecast → 28d sales avg + warning flag) |
| Safety stock | `SS = z·σ_daily·√P` (service level 95% → z 1.65; σ from 28d sales) |
| Usable inbound | open POs (placed/confirmed) with ETA ≤ today+P; **overdue excluded + flagged** |
| Inventory position | `IP = (on_hand − reserved) + usable_inbound` |
| Target / need | `T = D_P + SS`, `N = max(0, T − IP)` |
| Valid qty | `Q = 0` if N=0 else `ceil(max(N, MOQ)/case)·case` |
| Storage cap | **zone-level projection at arrival**: capacity − Σ(zone SKUs projected stock at arrival incl. their inbound and forecast depletion); conservative; floor to case |
| Budget cap | `floor_case(budget_remaining / unit_cost)` |
| Shelf-life cap | perishables: sellable within usable shelf life minus stock on hand at arrival; floor to case |
| Stockout before arrival | available + inbound_before_L − D_L < 0 → flag (order can't prevent it) |
| Final | `Q > min(caps)` → if min(caps) ≥ MOQ: capped qty (partial coverage flag) else no valid PO → resolution options / ESCALATE |
| Accept rule | rec feasible and `|rec − Q| ≤ max(1 case, 10%)` → ACCEPT |

**Worked example (C10)**: Aashirvaad Atta 5kg @ Andheri-W, rec 800 · forecast 40/d, σ 10, L 4, R 7 → P 11 ·
D_P 440, SS 55, T 495 · on_hand 180, reserved 10 → 170 · open PO 120 (ETA d+2) counted, PO 60 overdue
excluded · IP 290 → N 205 → MOQ 100 / case 10 → **Q 210** · storage free at arrival ~540 (800 overflows) ·
budget ₹1,50,000 (800×₹240 = ₹1,92,000 ✗; 210 → ₹50,400 ✓) · stock at arrival 340 = 8.5 days cover ✓ →
**MODIFY 210**, chase overdue PO.

### 7.2 Hard vs soft (D18/D19)
Hard (validator blocks; reasons never bypass): budget, storage, shelf life, MOQ, case pack.
Soft (override with reason): safety stock/service level, order cycle/target cover, accept tolerance,
max cover, max deviation from rec, preferred supplier.

### 7.3 Resolution options when blocked (dict dispatch per constraint; each pre-validated)
| Blocked by | Options |
|---|---|
| Budget | Order max affordable · **Request ₹X more budget** (change request) · Escalate |
| Storage | Order what fits · **Split into 2 deliveries** (2nd after depletion) · **Request N units space** · Escalate |
| Shelf life | Order what sells before expiry · Split into smaller frequent deliveries · Escalate (no request — expiry can't change) |
| MOQ | Order MOQ (if caps allow) · **Ask supplier for lower MOQ** · Skip & combine with next cycle · Escalate |
| Case pack | Nearest valid quantities (e.g. 768 / 816) |
| Multiple | Combined option satisfying all (recommended) + one request option per blocking constraint |
Change request approved by manager → data updated (audit) → automatic re-run.

### 7.4 Edge cases (each = seeded SKU×node + eval case)
**Decision**: C1 Coca-Cola 750ml@Bandra rec correct → ACCEPT 800 · C2 Parle-G@Powai open POs cover → REJECT ·
C3 Tata Tea@Thane ignores open PO → MODIFY↓ · C4 Maggi@Thane under-rec → MODIFY↑ · C5 Tata Salt@Lower Parel
need 70 < MOQ 150 → MODIFY 150 · C6 Red Bull@Bandra case 48 → MODIFY 816 · C7 Fortune Oil@Andheri-W budget
fits 500 → MODIFY 500 + partial · C8 Surf Excel@Bandra storage fits 400 → MODIFY 400 · C9 Haldiram@Powai MOQ
500 > budget-fit 300 → ESCALATE + options · C10 Atta@Andheri-W multi-constraint → MODIFY 210 · C11 Amul Taaza
@Powai shelf life 3d → MODIFY↓.
**Data quality**: Q1 Britannia Bread@Powai stale snapshot >24h → INVESTIGATE · Q2 Kurkure@Thane negative
on-hand → INVESTIGATE · Q3a Dairy Milk@Bandra no forecast → sales-avg fallback + flag · Q3b no forecast &
no sales → INVESTIGATE · Q4 Lay's@Andheri-W overdue PO → exclude + flag + decide · Q5 Bisleri@Lower Parel
supplier inactive → ESCALATE · Q6 Amul Butter@Thane forecast 2× sales → flag, >50% gap → INVESTIGATE ·
Q7 Dettol@Bandra prompt-injection note → treated as data, ignored, flagged.
**Reliability**: R1 duplicate run request → same run · R2 double approve → one PO · R3 invalid LLM JSON →
retry → fallback · R4 LLM qty violates constraint → validator → revise · R5 Groq down → Gemini · R6 worker
crash → resume from checkpoint · R7 reviewer fails twice → ESCALATE.
**Feedback loop (ERP)**: F1 price +8% breaks budget → cancel draft, re-plan → new proposal · F2 case pack
10→12 → re-propose · F3 timeout after create → retry same key, no duplicate · F4 ERP reject → escalate ·
F5 late ETA → recompute cover → accept with note / stockout flag · F6 mismatch after submit → cancel/amend
proposal for human approval.
**Learning**: L1 buyer modifies milk 600→500 "Powai weekends slower" → lesson confirmed → applied & cited
next run · L2 lesson violating hard constraint → ignored + explained · L3 disabled lesson → not applied.
**Resolution**: X1 storage-blocked → request space → manager approves → auto re-run passes · X2 buyer types
805 (case 48) → snap 768/816 · X3 buyer override of soft policy with reason → allowed + audited · X4 reason
alone on hard constraint → blocked.

### 7.5 Evaluation
Layers: (1) calculator/validator **unit tests** — exact numbers, no LLM; (2) **graph tests with scripted fake
LLM** — every path deterministic, CI-safe; (3) **live agent eval** — real models, each case ×3.
Checks: verdict ∈ expected · qty in band · required tools called · **constraints re-checked independently by
the eval** · correct action · explanation grounded (numbers match facts in code; optional Gemini judge) ·
verification performed · recovery path taken · cost/latency recorded.
Headline: decision accuracy · **hard-constraint violations in submitted POs = 0** · escalation rate ·
reviewer disagreement rate · avg cost/run. CLI `python -m app.evaluation run --scenario 1` + UI page.

## 8. Later scenarios (notes)
- **S2** (500 ordered, supplier confirms 250): recompute coverage with 250; options = accept partial,
  backorder, alternate supplier PO, **inter-node transfer**, escalate; update original PO to confirmed qty.
  New options plug into §7.3 dispatch. Needs `seed_scenario2.py`, alternate suppliers, reliability.
- **S3** (demand spike): trend vs one-off vs promo vs stockout-censored sales; days of cover vs PO ETA;
  increase/expedite PO, extra PO, watch. Optional M5-derived demand curves.

## 9. Session plan & next-session prompt

| Session | Phases (§10) | Ends with |
|---|---|---|
| **A** | P0–P6: repo hygiene, backend skeleton, DB, models + migrations, seed + mock ERP, calculator, validator | PR `feat/s1-core` → `develop`; all C/Q cases pass as unit tests |
| **B** | P7–P11: infra adapters, LLM layer, agent graph, runs API + worker, approval + ERP loop | PR `feat/s1-agent` → `develop`; graph tests (fake LLM) for R/F cases |
| **C** | P12–P15: memory/learning, auth + notifications, observability, evaluation runner | PR `feat/s1-platform` → `develop`; first live eval report |
| **D** | P16–P17: frontend foundation + all S1 pages | PR `feat/s1-frontend` → `develop` |
| **E** | P18–P20: docker/scripts/Railway, docs, full verify + reviews | PR `develop` → `main` (user merges) |
| S2, S3 | own deep-dive + build sessions | — |

Clear the session (`/clear`) between sessions; update §12 (progress) at the end of each.

**Next-session prompt (Session A):**
"Read `KNOWLEDGE_BASE.md` (all decisions agreed — don't re-litigate). We are in **Session A** (§9/§10:
P0–P6). Enter Plan Mode, turn P0–P6 into a concrete plan (files, tests-first list per phase, commit list per
§11), run plan-advisor once, get my approval, then build on branch `feat/s1-core` from `develop` with small
commits. Update §12 when done."

## 10. Implementation plan (shared foundation + Scenario 1)

Each phase = several small commits, tests first where logic exists (TDD for P5/P6 and all logic after).
| Phase | Scope | Key tests |
|---|---|---|
| P0 | `develop` branch, `.gitignore`, `.env.example`, `.editorconfig`, README skeleton, `config/settings.yaml` | — |
| P1 | Backend skeleton: uv project, app factory, settings (env + YAML), JSON logging, error handlers, `/health` | settings load, health |
| P2 | DB layer: async engine/session, Base, DB-mode resolution (Postgres / SQLite), Alembic portable setup | engine per mode |
| P3 | Domain ORM models + Pydantic DTOs + initial migration (§4 purchasing tables) | migration up on SQLite |
| P4 | `seed_scenario1.py` (all §7.4 cases) + mock ERP module (draft/submit/cancel/get, idempotency, surprise behaviours) | seed idempotent; ERP idempotency + each behaviour |
| P5 | Calculator + options generator + split delivery (pure) | every C/Q case exact numbers; worked example |
| P6 | Validator (hard/soft, consistency, deviation) + data-quality checks | X2–X4, Q1–Q7, R4 |
| P7 | Infra adapters: cache, queue (inproc/Arq), broadcaster, idempotency service | swap by config |
| P8 | LLM layer: provider factory, Groq/Gemini, fallback, structured output, `llm_calls` + cost, fault injection, scripted fake LLM | R3, R5 |
| P9 | Agent graph nodes 1–9, checkpointer, prompts | graph paths with fake LLM, R7 |
| P10 | Runs API + worker, status machine, resume on startup, `tool_calls` audit | R1, R6 |
| P11 | Approvals, human_gate, change requests, ERP execute/verify/deviation/submit/verify | R2, F1–F6, X1 |
| P12 | Memory: episodes, lessons (pending→confirmed), recall | L1–L3 |
| P13 | Auth (JWT cookie, roles), users seed, notifications + SSE | auth, role guard |
| P14 | Observability: cost/metrics API, Langfuse optional | aggregation |
| P15 | Evaluation: case definitions, runner CLI, results tables + API | runner on fake LLM |
| P16 | Frontend foundation: Next.js, Tailwind tokens, layout/nav, auth, generated API client, notifications | — |
| P17 | Frontend pages: Home, Inbox, Review, POs, Memory, Change requests, Admin, Evaluation | key flows manual + smoke |
| P18 | `docker-compose.yml`, `scripts/run_*.sh` (mode detection), Railway config | run in both modes |
| P19 | Docs: architecture (Mermaid), scenario-1, evaluation, decisions, deployment, README | — |
| P20 | Full verify (lint, types, tests), adversarial + architecture review, fix pass, PR `develop` → `main` | all green |

## 11. Git workflow & commit culture
- `main` is protected by convention: **never commit/push directly to main**. Integration branch **`develop`**.
- One feature branch per session (`feat/s1-core`, `feat/s1-agent`, …) → PR into `develop`. Final PR
  `develop` → `main` is merged by the user.
- **Small commits, one logical change each**, Conventional Commits: `type(scope): imperative summary`
  (`feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `build`). Body explains **why** in 1–3 lines.
  Example: `feat(planning): add net-need calculation with safety stock` / body: "Pure function so the LLM
  never does arithmetic; covers C1–C5."
- Tests-first visible in history where sensible (`test(planning): …` then `feat(planning): …`).
- Never commit secrets; `.env` git-ignored; `.env.example` documented.

## 12. Progress
- 2026-10-14: discovery + S1 deep dive complete; KB written; repo created (`main` @ 02beaf6).
