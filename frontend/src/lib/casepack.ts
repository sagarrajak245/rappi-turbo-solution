export interface CasePackSnap {
  valid: boolean;
  /** Valid quantities: the qty itself when valid, else nearest multiples below and above. */
  suggestions: number[];
}

export function snapToCasePack(qty: number, pack: number): CasePackSnap {
  if (pack <= 0) return { valid: true, suggestions: [qty] };
  if (qty > 0 && qty % pack === 0) return { valid: true, suggestions: [qty] };
  const below = Math.floor(qty / pack) * pack;
  const above = below + pack;
  return { valid: false, suggestions: below >= pack ? [below, above] : [above] };
}
