"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { api, unwrap } from "@/lib/api/client";
import { useMe } from "@/lib/hooks";
import { formatInr, pct } from "@/lib/format";
import { Card, ErrorState, Kpi, PageTitle, StripedBar, VerdictBadge } from "@/components/ui";

export default function HomePage() {
  const me = useMe();
  const summary = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => unwrap(await api.GET("/dashboard/summary")),
    refetchInterval: 15_000,
  });
  const activity = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => unwrap(await api.GET("/notifications")),
  });

  const d = summary.data;
  const firstName = me.data?.name?.split(" ")[0] ?? "there";

  return (
    <>
      <PageTitle title={`Hi, ${firstName}`} subtitle="Here is what needs you today." />
      {summary.isError && (
        <ErrorState message={summary.error.message} onRetry={() => summary.refetch()} />
      )}
      {d && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Pending approvals" value={d.pending_approvals} />
            <Kpi label="Committed today" value={formatInr(d.committed_today_inr)} />
            <Kpi
              label="Agent agreement"
              value={d.agreement_pct === null ? "—" : `${d.agreement_pct}%`}
              hint="Approved as proposed"
            />
            <Kpi label="Needs attention" value={d.needs_attention} hint="Failed after the ERP" />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card dark className="lg:col-span-2">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg">Needs your decision</h2>
                <Link href="/inbox" className="text-sm text-white/70 hover:text-white">
                  Inbox
                </Link>
              </div>
              {d.needs_decision.length === 0 && (
                <p className="text-white/60">Nothing waiting. Run the agent from the inbox.</p>
              )}
              <ul className="divide-y divide-white/10">
                {d.needs_decision.map((r) => (
                  <li key={r.id}>
                    <Link
                      href={`/runs/${r.id}`}
                      className="flex items-center gap-4 py-3 hover:opacity-80"
                    >
                      <VerdictBadge verdict={r.verdict ?? null} outcome={r.outcome} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate">
                          {r.sku} at {r.node} · {r.qty ?? "—"} units
                        </p>
                        {r.reason && <p className="truncate text-sm text-white/60">{r.reason}</p>}
                      </div>
                      <ArrowRight className="h-4 w-4 shrink-0" />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              <h2 className="mb-4 text-lg">Activity</h2>
              {activity.data?.length === 0 && <p className="text-neutral-500">No activity yet.</p>}
              <ol className="space-y-3">
                {activity.data?.slice(0, 6).map((n) => (
                  <li key={n.id} className="border-l-2 border-[#F5D547] pl-3 text-sm">
                    {n.run_id ? <Link href={`/runs/${n.run_id}`}>{n.message}</Link> : n.message}
                    <p className="text-xs text-neutral-400">
                      {new Date(n.created_at).toLocaleString()}
                    </p>
                  </li>
                ))}
              </ol>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <h2 className="mb-4 text-lg">Budget this month</h2>
              <div className="space-y-4">
                {d.budgets.map((b) => (
                  <div key={b.node}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span>{b.node}</span>
                      <span className="text-neutral-500">
                        {formatInr(b.used_inr)} / {formatInr(b.limit_inr)}
                      </span>
                    </div>
                    <StripedBar value={pct(b.used_inr, b.limit_inr)} />
                  </div>
                ))}
              </div>
            </Card>
            <Card>
              <h2 className="mb-4 text-lg">Storage used</h2>
              <div className="space-y-4">
                {d.storage.map((s) => (
                  <div key={s.node}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span>{s.node}</span>
                      <span className="text-neutral-500">{pct(s.used, s.capacity)}%</span>
                    </div>
                    <StripedBar value={pct(s.used, s.capacity)} />
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {["Scenario 2 · Supplier delays", "Scenario 3 · Price changes"].map((t) => (
              <Card key={t} className="opacity-60">
                <p className="font-medium">{t}</p>
                <p className="text-sm text-neutral-500">Coming soon</p>
              </Card>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
