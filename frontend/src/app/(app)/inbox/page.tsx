"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { toast } from "sonner";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { Card, EmptyState, ErrorState, PageTitle, StatusBadge, VerdictBadge } from "@/components/ui";

type Row = Schemas["InboxRow"];
type RunStatus = Schemas["RunStatus"];

const BUSY: RunStatus[] = ["running", "executing"];
const STATUSES: RunStatus[] = ["awaiting_approval", "running", "completed", "rejected", "acknowledged", "escalated", "needs_human", "failed"];

const isBusy = (r: Row) => !!r.run && BUSY.includes(r.run.status);

export default function InboxPage() {
  const qc = useQueryClient();
  const [node, setNode] = useState("");
  const [status, setStatus] = useState<RunStatus | "">("");

  const rows = useQuery({
    queryKey: ["inbox", node, status],
    queryFn: async () =>
      unwrap(
        await api.GET("/recommendations", {
          params: { query: { node: node || undefined, status: status || undefined } },
        }),
      ),
    // keep polling while any agent run is still deciding or executing
    refetchInterval: (q) => (q.state.data?.some(isBusy) ? 2_000 : false),
  });

  const nodes = useQuery({
    queryKey: ["inbox", "", ""],
    queryFn: async () => unwrap(await api.GET("/recommendations")),
    select: (all) => [...new Set(all.map((r) => r.node))].sort(),
  });

  const start = useMutation({
    mutationFn: async (targets: Row[]) => {
      for (const r of targets) {
        unwrap(await api.POST("/agent/runs", { body: { sku: r.sku, node: r.node } }));
      }
      return targets.length;
    },
    onSuccess: (n) => toast.success(n === 1 ? "Agent started" : `Agent started on ${n} items`),
    onError: (e: Error) => toast.error(e.message),
    onSettled: () => qc.invalidateQueries({ queryKey: ["inbox"] }),
  });

  const runnable = useMemo(
    () => (rows.data ?? []).filter((r) => !isBusy(r) && r.run?.status !== "awaiting_approval"),
    [rows.data],
  );

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <PageTitle title="Inbox" subtitle="Upstream recommendations and what the agent made of them." />
        <button
          disabled={start.isPending || runnable.length === 0}
          onClick={() => start.mutate(runnable)}
          className="flex items-center gap-2 rounded-full bg-[#1F1F1F] px-5 py-2.5 text-sm text-white disabled:opacity-50"
        >
          <Play className="h-4 w-4" /> Run all ({runnable.length})
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-3">
        <select
          aria-label="Node"
          value={node}
          onChange={(e) => setNode(e.target.value)}
          className="rounded-full bg-white/70 px-4 py-2 text-sm"
        >
          <option value="">All nodes</option>
          {nodes.data?.map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
        <select
          aria-label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value as RunStatus | "")}
          className="rounded-full bg-white/70 px-4 py-2 text-sm"
        >
          <option value="">Any status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </div>

      {rows.isLoading && <p className="text-neutral-500">Loading...</p>}
      {rows.isError && <ErrorState message={rows.error.message} onRetry={() => rows.refetch()} />}
      {rows.data?.length === 0 && <EmptyState title="Nothing matches" hint="Try another filter." />}
      {!!rows.data?.length && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-neutral-500">
              <tr>
                {["Product", "Node", "Rec qty", "Agent", "Agent qty", "Status", "Why", ""].map((h) => (
                  <th key={h} className="px-4 py-3 font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.data.map((r) => (
                <tr key={r.recommendation_id} className="border-t border-neutral-200/70 align-top">
                  <td className="px-4 py-3">
                    <p>{r.product_name}</p>
                    <p className="font-mono text-xs text-neutral-500">{r.sku}</p>
                  </td>
                  <td className="px-4 py-3">{r.node}</td>
                  <td className="px-4 py-3">{r.rec_qty}</td>
                  <td className="px-4 py-3">
                    {r.run?.verdict || r.run?.outcome ? (
                      <VerdictBadge verdict={r.run.verdict ?? null} outcome={r.run.outcome} />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3">{r.run?.qty ?? "—"}</td>
                  <td className="px-4 py-3">{r.run ? <StatusBadge status={r.run.status} /> : "—"}</td>
                  <td className="max-w-xs px-4 py-3 text-neutral-600">
                    <span className="line-clamp-2">{r.run?.reason ?? r.run?.error ?? ""}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    {r.run && !isBusy(r) && (
                      <Link href={`/runs/${r.run.id}`} className="mr-3 underline">
                        {r.run.status === "awaiting_approval" ? "Review" : "Open"}
                      </Link>
                    )}
                    {isBusy(r) ? (
                      <span className="text-neutral-500">Working…</span>
                    ) : (
                      r.run?.status !== "awaiting_approval" && (
                        <button
                          disabled={start.isPending}
                          onClick={() => start.mutate([r])}
                          className="rounded-full bg-[#F5D547] px-3 py-1.5 disabled:opacity-50"
                        >
                          Run agent
                        </button>
                      )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
