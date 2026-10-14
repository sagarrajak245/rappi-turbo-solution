"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Card, EmptyState, ErrorState, PageTitle, StatusBadge } from "@/components/ui";

type Status = "pending" | "active" | "disabled";
const TABS: { id: Status; label: string }[] = [
  { id: "pending", label: "Needs review" },
  { id: "active", label: "Active" },
  { id: "disabled", label: "Disabled" },
];

export default function MemoryPage() {
  const [tab, setTab] = useState<Status>("pending");
  const qc = useQueryClient();

  const lessons = useQuery({
    queryKey: ["lessons", tab],
    queryFn: async () => unwrap(await api.GET("/memory/lessons", { params: { query: { status: tab } } })),
  });

  const act = useMutation({
    mutationFn: async ({ id, action }: { id: number; action: "confirm" | "disable" }) => {
      const path = action === "confirm" ? "/memory/lessons/{lesson_id}/confirm" : "/memory/lessons/{lesson_id}/disable";
      const res = await api.POST(path, { params: { path: { lesson_id: id } } });
      if (res.error !== undefined) {
        throw Object.assign(new Error(errorMessage(res.error)), { status: res.response.status });
      }
    },
    onSuccess: (_d, v) => {
      toast.success(v.action === "confirm" ? "Lesson confirmed" : "Lesson disabled");
      qc.invalidateQueries({ queryKey: ["lessons"] });
    },
    onError: (e: Error & { status?: number }) => {
      if (e.status === 409) {
        toast.error("This lesson was already handled. Refreshing the list.");
        qc.invalidateQueries({ queryKey: ["lessons"] });
      } else {
        toast.error(e.message);
      }
    },
  });

  return (
    <>
      <PageTitle title="Memory" subtitle="What the agent has learned from your past decisions." />
      <div className="mb-5 inline-flex gap-1 rounded-full bg-white/70 p-1.5 shadow-sm">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "rounded-full px-4 py-2 text-sm",
              tab === t.id ? "bg-black text-white" : "text-neutral-600",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {lessons.isLoading && <p className="text-neutral-500">Loading...</p>}
      {lessons.isError && <ErrorState message={lessons.error.message} onRetry={() => lessons.refetch()} />}
      {lessons.data?.length === 0 && <EmptyState title="Nothing here" hint="No lessons in this tab yet." />}
      <div className="space-y-3">
        {lessons.data?.map((l) => (
          <Card key={l.id} className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center gap-2">
                <StatusBadge status={l.status} />
                <span className="text-xs text-neutral-500">
                  {l.sku} at {l.node} - used {l.times_applied}x
                </span>
              </div>
              <p>{l.text}</p>
            </div>
            <div className="flex gap-2">
              {l.status === "pending" && (
                <button
                  disabled={act.isPending}
                  onClick={() => act.mutate({ id: l.id, action: "confirm" })}
                  className="rounded-full bg-[#1F1F1F] px-4 py-2 text-sm text-white disabled:opacity-60"
                >
                  Confirm
                </button>
              )}
              {l.status !== "disabled" && (
                <button
                  disabled={act.isPending}
                  onClick={() => act.mutate({ id: l.id, action: "disable" })}
                  className="rounded-full bg-neutral-200 px-4 py-2 text-sm disabled:opacity-60"
                >
                  Disable
                </button>
              )}
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
