// Regenerates openapi.json from the FastAPI app, then the TS schema types.
import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const backend = path.resolve(root, "..", "backend");

const json = execSync(
  `python -m uv run python -c "import json;from app.main import create_app;print(json.dumps(create_app().openapi()))"`,
  { cwd: backend, encoding: "utf8", maxBuffer: 64 * 1024 * 1024, stdio: ["ignore", "pipe", "inherit"] },
);
writeFileSync(path.join(root, "openapi.json"), json.trim() + "\n");
execSync("pnpm exec openapi-typescript openapi.json -o src/lib/api/schema.d.ts", {
  cwd: root,
  stdio: "inherit",
});
