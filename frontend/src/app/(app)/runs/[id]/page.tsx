"use client";

import { use } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Card, ErrorState, PageTitle, StatusBadge, VerdictBadge } from "@/components/ui";
import { DecisionPanel } from "./decision-panel";
import { ProjectionChart } from "./projection-chart";

type Run = Schemas["RunOut"];
type Proposal = Schemas["ProposalOut"];

const BUSY = ["running", "executing"];

const FACTS: [key: string, label: string][] = [
  ["demand_daily", "Demand / day"],
  ["safety_stock", "Safety stock"],
  ["on_hand", "On hand"],
  ["reserved", "Reserved"],
  ["inventory_position", "Inventory position"],
  ["stock_at_arrival", "Stock at arrival"],
  ["cover_days", "Cover after order (days)"],
  ["need_qty", "Calculated need"],
  ["moq", "MOQ"],
  ["case_pack", "Case pack"],
  ["lead_time_days", "Lead time (days)"],
  ["protection_days", "Protection period (days)"],
];

type Decision = NonNullable<Run["decision"]>;

function inShort(p: Proposal, d: Decision | null | undefined): string {
  if (d?.action === "modify" && d.qty != null)
    return d.qty === 0 ? `You chose not to order (the agent proposed ${p.qty}).` : `You ordered ${d.qty} instead of the agent's ${p.qty}.`;
  if (d?.action === "reject") return "You rejected this proposal; nothing was ordered.";
  if (p.outcome === "ESCALATE") return "No valid order fits the limits; a person has to choose a way out.";
  if (p.verdict === "INVESTIGATE") return "The data is not trustworthy enough to order; investigate first.";
  if (p.verdict === "REJECT") return `Don't order: the recommended ${p.rec_qty} is not needed.`;
  if (p.verdict === "ACCEPT") return `Order ${p.qty} as recommended.`;
  return `Order ${p.qty} instead of the recommended ${p.rec_qty}.`;
}

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: async () => unwrap(await api.GET("/agent/runs/{run_id}", { params: { path: { run_id: id } } })),
    refetchInterval: (q) => (q.state.data && BUSY.includes(q.state.data.status) ? 2_000 : false),
  });

  if (run.isLoading) return <p className="text-neutral-500">Loading...</p>;
  if (run.isError) return <ErrorState message={run.error.message} onRetry={() => run.refetch()} />;
  const r = run.data!;
  const p = r.proposal;

  return (
    <>
      <div className="mb-2 text-sm">
        <Link href="/inbox" className="text-neutral-500 hover:underline">
          ← Inbox
        </Link>
      </div>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <PageTitle title={`${r.sku} at ${r.node}`} />
        <StatusBadge status={r.status} />
        {p && <VerdictBadge verdict={p.verdict ?? null} outcome={p.outcome} />}
      </div>

      {!p && (
        <Card>
          {BUSY.includes(r.status) ? "The agent is working on it…" : (r.error ?? "No proposal.")}
        </Card>
      )}

      {p && (
        <div className="space-y-6">
          <Card dark>
            <p className="text-sm text-white/60">In short</p>
            <p className="mt-1 text-2xl font-light">{inShort(p, r.decision)}</p>
            {r.decision?.reason && <p className="mt-2 text-white/80">Your reason: {r.decision.reason}</p>}
            <ul className="mt-3 list-disc space-y-1 pl-5 text-white/80">
              {p.reasons.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
            {p.lessons_applied.length > 0 && (
              <p className="mt-3 text-sm text-[#F5D547]">
                Used {p.lessons_applied.length} lesson(s) from your past decisions.
              </p>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <h2 className="mb-2 text-lg">Next 14 days</h2>
              {p.projection ? (
                <ProjectionChart projection={p.projection} />
              ) : (
                <p className="text-neutral-500">No projection for this run.</p>
              )}
            </Card>
            <Card>
              <h2 className="mb-3 text-lg">Facts</h2>
              <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
                {FACTS.filter(([k]) => p.facts[k] !== undefined && p.facts[k] !== null).map(([k, label]) => (
                  <FactRow key={k} label={label} value={String(p.facts[k])} />
                ))}
              </dl>
              <Caps caps={p.facts.caps} />
            </Card>
          </div>

          {(p.flags.length > 0 || p.issues.length > 0) && (
            <Card>
              <h2 className="mb-3 text-lg">Flags and issues</h2>
              <div className="flex flex-wrap gap-2">
                {p.flags.map((f) => (
                  <span
                    key={f.code}
                    title={f.message}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs",
                      f.severity === "blocking" ? "bg-[#FF441F]/15 text-[#C2300F]" : "bg-[#F5D547]/40",
                    )}
                  >
                    {f.message}
                  </span>
                ))}
              </div>
              {p.issues.length > 0 && (
                <ul className="mt-3 list-disc pl-5 text-sm text-neutral-600">
                  {p.issues.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              )}
            </Card>
          )}

          {p.options.length > 0 && (
            <Card>
              <h2 className="mb-3 text-lg">Ways out</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {p.options.map((o, i) => (
                  <div
                    key={o.kind}
                    className={cn("rounded-2xl p-4", i === 0 ? "bg-[#F5D547]/40 ring-2 ring-[#F5D547]" : "bg-neutral-100")}
                  >
                    {i === 0 && <p className="mb-1 text-xs font-medium">Recommended</p>}
                    <p className="font-medium">{o.description}</p>
                    <p className="text-sm text-neutral-600">
                      {o.qty} units{o.requires ? ` · needs ${o.requires}` : ""}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {r.status === "awaiting_approval" && <DecisionPanel run={r} proposal={p} />}
          {r.error && r.status === "awaiting_approval" && (
            <p className="text-sm text-[#C2300F]">Last attempt: {r.error}</p>
          )}

          <Result run={r} />
          <RememberThis runId={r.id} />

          <details className="rounded-[24px] bg-white/50 p-6">
            <summary className="cursor-pointer">How the agent got here</summary>
            <dl className="mt-3 grid max-w-md grid-cols-2 gap-x-8 gap-y-1.5 text-sm">
              <FactRow label="Review attempts" value={String(p.attempts)} />
              <FactRow label="LLM calls" value={String(p.llm_calls)} />
              <FactRow label="System qty" value={String(p.baseline_qty ?? "—")} />
              <FactRow label="Re-plans" value={String(r.replans_done)} />
            </dl>
            {p.deviation_reason && <p className="mt-3 text-sm">Deviation: {p.deviation_reason}</p>}
          </details>
        </div>
      )}
    </>
  );
}

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-neutral-500">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </>
  );
}

function Caps({ caps }: { caps: unknown }) {
  const entries = Object.entries((caps ?? {}) as Record<string, number>);
  if (entries.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="mb-2 text-sm text-neutral-500">Max allowed by</p>
      <div className="flex flex-wrap gap-2">
        {entries.map(([code, cap]) => (
          <span key={code} className="rounded-full bg-neutral-100 px-3 py-1 text-xs">
            {code.replaceAll("_", " ")}: {cap}
          </span>
        ))}
      </div>
    </div>
  );
}

function Result({ run }: { run: Run }) {
  const ex = run.execution;
  if (!ex && !["completed", "rejected", "acknowledged", "needs_human", "escalated", "failed"].includes(run.status))
    return null;
  return (
    <Card>
      <h2 className="mb-3 text-lg">Result</h2>
      {!ex && <p className="text-neutral-600">{run.error ?? `This run is ${run.status.replaceAll("_", " ")}.`}</p>}
      {ex && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            {["draft", "submitted", "verified"].map((step, i) => (
              <span key={step} className="flex items-center gap-2">
                {i > 0 && <span className="text-neutral-400">→</span>}
                <span
                  className={cn(
                    "rounded-full px-3 py-1",
                    ex.erp_number && (step !== "verified" || ex.status === "completed")
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-neutral-100 text-neutral-500",
                  )}
                >
                  {step}
                </span>
              </span>
            ))}
            <StatusBadge status={ex.status} />
          </div>
          {ex.erp_number && (
            <p className="text-sm">
              ERP order <span className="font-mono">{ex.erp_number}</span> · {run.decision?.qty ?? run.proposal?.qty} units ·{" "}
              {ex.final_status}
            </p>
          )}
          {ex.deviations.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm">
              {ex.deviations.map((d) => (
                <li key={d.field}>
                  {d.field}: expected {d.expected}, ERP has {d.actual} ({d.severity})
                </li>
              ))}
            </ul>
          )}
          {ex.notes.map((n) => (
            <p key={n} className="mt-1 text-sm text-neutral-600">
              {n}
            </p>
          ))}
          {ex.status === "replan_required" && (
            <p className="mt-2 text-sm">The ERP changed terms; the agent re-planned and needs your review again.</p>
          )}
        </>
      )}
    </Card>
  );
}

/** After a reasoned modify or reject, the backend drafts a pending lesson from this run. */
function RememberThis({ runId }: { runId: string }) {
  const qc = useQueryClient();
  const pending = useQuery({
    queryKey: ["lessons", "pending"],
    queryFn: async () => unwrap(await api.GET("/memory/lessons", { params: { query: { status: "pending" } } })),
    select: (all) => all.find((l) => l.source_run_id === runId),
  });
  const confirm = useMutation({
    mutationFn: async (lessonId: number) =>
      unwrap(await api.POST("/memory/lessons/{lesson_id}/confirm", { params: { path: { lesson_id: lessonId } } })),
    onSuccess: () => {
      toast.success("Remembered. The agent will use this next time.");
      qc.invalidateQueries({ queryKey: ["lessons"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const lesson = pending.data;
  if (!lesson) return null;
  return (
    <Card className="ring-2 ring-[#F5D547]">
      <p className="mb-1 font-medium">Remember this?</p>
      <p className="mb-4 text-neutral-600">{lesson.text}</p>
      <button
        disabled={confirm.isPending}
        onClick={() => confirm.mutate(lesson.id)}
        className="rounded-full bg-[#1F1F1F] px-5 py-2.5 text-sm text-white disabled:opacity-50"
      >
        Yes, remember it
      </button>
    </Card>
  );
}
