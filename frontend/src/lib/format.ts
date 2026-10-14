/** Money and ratios arrive from the API as decimal strings (exact), or numbers. */
type Num = number | string;

export function formatInr(value: Num): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

/** Whole percent of used/limit, clamped to 0..100; 0 when there is no limit. */
export function pct(used: Num, limit: Num): number {
  const l = Number(limit);
  if (!(l > 0)) return 0;
  return Math.max(0, Math.min(100, Math.round((100 * Number(used)) / l)));
}
