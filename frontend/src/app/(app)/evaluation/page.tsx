"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { api, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Card, EmptyState, ErrorState, PageTitle, StripedBar } from "@/components/ui";

/** A check value may be a bare boolean or an object carrying `passed`. */
function checkPassed(v: unknown): boolean {
  if (typeof v === "boolean") return v;
  if (v && typeof v === "object" && "passed" in v) return Boolean((v as { passed: unknown }).passed);
  return false;
}

function RunDetail({ id }: { id: number }) {
  const q = useQuery({
    queryKey: ["eval-run", id],
    queryFn: async () => unwrap(await api.GET("/evaluation/runs/{run_id}", { params: { path: { run_id: id } } })),
  });
  if (q.isLoading) return <p className="text-neutral-500">Loading...</p>;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  const run = q.data!;
  const checkNames = Array.from(new Set(run.results.flatMap((r) => Object.keys(r.checks))));
  const passed = run.results.filter((r) => r.passed).length;

  return (
    <Card className="overflow-x-auto">
      <div className="mb-4 flex items-center gap-4">
        <h2 className="font-medium">
          {run.scenario} <span className="text-sm text-neutral-500">({run.mode})</span>
        </h2>
        <span className="text-sm text-neutral-500">
          {passed}/{run.results.length} cases passed
        </span>
        <StripedBar className="max-w-48" value={run.results.length ? (passed / run.results.length) * 100 : 0} />
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-neutral-500">
            <th className="pb-2 pr-4 font-normal">Case</th>
            {checkNames.map((c) => (
              <th key={c} className="pb-2 pr-4 font-normal">
                {c.replaceAll("_", " ")}
              </th>
            ))}
            <th className="pb-2 font-normal">Result</th>
          </tr>
        </thead>
        <tbody>
          {run.results.map((r) => (
            <tr key={r.id} className="border-t border-neutral-200/70">
              <td className="py-2 pr-4">
                <span className="font-medium">{r.case_id}</span>
                <span className="ml-2 text-xs text-neutral-500">
                  {r.sku} at {r.node}
                </span>
              </td>
              {checkNames.map((c) => (
                <td key={c} className="py-2 pr-4">
                  {c in r.checks ? (
                    checkPassed(r.checks[c]) ? (
                      <Check className="h-4 w-4 text-emerald-600" aria-label="pass" />
                    ) : (
                      <X className="h-4 w-4 text-[#FF441F]" aria-label="fail" />
                    )
                  ) : (
                    <span className="text-neutral-300">-</span>
                  )}
                </td>
              ))}
              <td className="py-2">
                <span className={cn("rounded-full px-3 py-1 text-xs", r.passed ? "bg-emerald-100 text-emerald-800" : "bg-[#FF441F]/15 text-[#C2300F]")}>
                  {r.passed ? "Pass" : "Fail"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export default function EvaluationPage() {
  const [selected, setSelected] = useState<number | null>(null);
  const runs = useQuery({
    queryKey: ["eval-runs"],
    queryFn: async () => unwrap(await api.GET("/evaluation/runs")),
  });

  return (
    <>
      <PageTitle title="Evaluation" subtitle="How the agent scores against known cases." />
      {runs.isLoading && <p className="text-neutral-500">Loading...</p>}
      {runs.isError && <ErrorState message={runs.error.message} onRetry={() => runs.refetch()} />}
      {runs.data?.length === 0 && <EmptyState title="No evaluation runs yet" />}
      <div className="mb-6 flex flex-wrap gap-3">
        {runs.data?.map((r) => (
          <button
            key={r.id}
            onClick={() => setSelected(r.id)}
            className={cn(
              "rounded-[24px] px-5 py-3 text-left shadow-sm",
              selected === r.id ? "bg-black text-white" : "bg-white/70",
            )}
          >
            <span className="block font-medium">{r.scenario}</span>
            <span className="text-xs opacity-60">
              #{r.id} - {r.mode} - {new Date(r.started_at).toLocaleString()}
            </span>
          </button>
        ))}
      </div>
      {selected !== null && <RunDetail id={selected} />}
    </>
  );
}
