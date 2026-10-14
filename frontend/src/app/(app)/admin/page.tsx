"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, unwrap } from "@/lib/api/client";
import { Card, ErrorState, Kpi, PageTitle, StatusBadge } from "@/components/ui";

const usd = (n: number) => `$${n.toFixed(n < 1 ? 4 : 2)}`;

export default function AdminPage() {
  const q = useQuery({
    queryKey: ["admin-metrics"],
    queryFn: async () => unwrap(await api.GET("/admin/metrics")),
  });

  if (q.isLoading) return <p className="text-neutral-500">Loading...</p>;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  const m = q.data!;
  const byModel = m.llm.map((l) => ({ name: l.model, cost: l.cost_usd, calls: l.calls }));

  return (
    <>
      <PageTitle title="Admin" subtitle="How the agent is running and what it costs." />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Total runs" value={m.total_runs} />
        <Kpi label="AI calls" value={m.total_llm_calls} />
        <Kpi label="Total cost" value={usd(m.total_cost_usd)} hint={`${usd(m.avg_cost_per_run)} per run`} />
        <Kpi label="Fallback rate" value={`${Math.round(m.fallback_rate * 100)}%`} hint="Calls that used the backup model" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 font-medium">Cost by model</h2>
          {byModel.length === 0 ? (
            <p className="text-sm text-neutral-500">No AI calls yet.</p>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byModel}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v) => usd(Number(v))} />
                  <Bar dataKey="cost" fill="#F5D547" radius={[12, 12, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
        <Card>
          <h2 className="mb-4 font-medium">Runs by status</h2>
          <ul className="space-y-2">
            {Object.entries(m.runs_by_status).map(([status, n]) => (
              <li key={status} className="flex items-center justify-between">
                <StatusBadge status={status} />
                <span className="text-2xl font-extralight">{n as number}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
