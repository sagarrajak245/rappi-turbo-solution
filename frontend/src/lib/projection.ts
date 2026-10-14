/** Shapes the backend's 14-day stock projection into chart rows (one per day). */
export interface ProjectionSeries {
  qty: number;
  stock: number[];
  stockout_day: number | null;
}

export interface StockProjection {
  no_order: ProjectionSeries;
  system: ProjectionSeries;
  agent: ProjectionSeries;
  buyer?: ProjectionSeries | null; // present once the buyer changed the quantity
  storage_ceiling: number | null;
}

export interface ProjectionRow {
  day: number;
  label: string;
  noOrder: number;
  system: number;
  agent: number;
  buyer?: number;
}

export function projectionRows(p: StockProjection | null | undefined): ProjectionRow[] {
  if (!p) return [];
  return p.no_order.stock.map((noOrder, day) => ({
    day,
    label: day === 0 ? "Today" : `D+${day}`,
    noOrder,
    system: p.system.stock[day] ?? 0,
    agent: p.agent.stock[day] ?? 0,
    ...(p.buyer && { buyer: p.buyer.stock[day] ?? 0 }),
  }));
}
