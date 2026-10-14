# E2E smoke

Needs a seeded backend; `next dev` is started by Playwright.

```sh
cd backend
python -m uv run alembic upgrade head && python -m uv run python -m app.seed scenario1
python -m uv run uvicorn app.main:create_app --factory --port 8000
cd ../frontend
pnpm exec playwright install chromium   # once
pnpm e2e                                # BACKEND_URL defaults to http://localhost:8000
```

Without LLM keys a run escalates within seconds, which is enough for the smoke path.
