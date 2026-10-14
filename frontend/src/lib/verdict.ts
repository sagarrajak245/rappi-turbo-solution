export type Verdict = "ACCEPT" | "MODIFY" | "REJECT" | "INVESTIGATE";
export type Tone = "green" | "yellow" | "coral" | "slate" | "red-outline";

export interface VerdictStyle {
  label: string;
  tone: Tone;
}

const BASE: Record<Verdict, VerdictStyle> = {
  ACCEPT: { label: "Accept", tone: "green" },
  MODIFY: { label: "Modify", tone: "yellow" },
  REJECT: { label: "Reject", tone: "coral" },
  INVESTIGATE: { label: "Investigate", tone: "slate" },
};

export function verdictStyle(verdict: Verdict, outcome?: string | null): VerdictStyle {
  if (outcome === "ESCALATED") return { label: "Escalated", tone: "red-outline" };
  return BASE[verdict];
}

export const TONE_CLASS: Record<Tone, string> = {
  green: "bg-emerald-100 text-emerald-800",
  yellow: "bg-[#F5D547]/40 text-yellow-900",
  coral: "bg-[#FF441F]/15 text-[#C2300F]",
  slate: "bg-slate-200 text-slate-700",
  "red-outline": "bg-white text-red-600 ring-1 ring-red-500",
};
