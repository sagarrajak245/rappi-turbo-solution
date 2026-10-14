import type { ReactNode } from "react";
import { AlertTriangle, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";
import { TONE_CLASS, verdictStyle, type Verdict } from "@/lib/verdict";

export function Card({
  children,
  className,
  dark,
}: {
  children: ReactNode;
  className?: string;
  dark?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-[24px] p-6 shadow-[0_8px_30px_rgba(31,31,31,0.06)]",
        dark ? "bg-[#1F1F1F] text-white" : "bg-white/70 backdrop-blur-md",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <Card>
      <p className="text-sm text-neutral-500">{label}</p>
      <p className="mt-2 text-5xl font-extralight tracking-tight">{value}</p>
      {hint && <p className="mt-1 text-xs text-neutral-400">{hint}</p>}
    </Card>
  );
}

export function StripedBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-3 w-full overflow-hidden rounded-full bg-neutral-200/70", className)}>
      <div className="striped h-full rounded-full bg-[#F5D547]" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function VerdictBadge({
  verdict,
  outcome,
}: {
  verdict: Verdict | null;
  outcome?: string | null;
}) {
  const s = verdictStyle(verdict, outcome);
  return (
    <span className={cn("rounded-full px-3 py-1 text-xs font-medium", TONE_CLASS[s.tone])}>
      {s.label}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-800",
  pending: "bg-[#F5D547]/40 text-yellow-900",
  disabled: "bg-slate-200 text-slate-600",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-[#FF441F]/15 text-[#C2300F]",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "rounded-full px-3 py-1 text-xs font-medium capitalize",
        STATUS_TONE[status] ?? "bg-neutral-200 text-neutral-700",
      )}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <Card className="flex flex-col items-center py-12 text-center">
      <Inbox className="mb-3 h-8 w-8 text-neutral-400" />
      <p className="font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-neutral-500">{hint}</p>}
    </Card>
  );
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <Card className="flex flex-col items-center py-12 text-center">
      <AlertTriangle className="mb-3 h-8 w-8 text-[#FF441F]" />
      <p className="font-medium">{message ?? "Something went wrong"}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-full bg-[#1F1F1F] px-4 py-2 text-sm text-white"
        >
          Try again
        </button>
      )}
    </Card>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-3xl font-light tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1 text-neutral-500">{subtitle}</p>}
    </div>
  );
}

export function ComingNext({ title }: { title: string }) {
  return (
    <>
      <PageTitle title={title} />
      <EmptyState title="Coming next" hint="This page is being built." />
    </>
  );
}
