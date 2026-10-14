import { describe, expect, it } from "vitest";
import { projectionRows } from "./projection";

const series = (qty: number, stock: number[], stockout_day: number | null = null) => ({
  qty,
  stock,
  stockout_day,
});

describe("projectionRows", () => {
  it("zips the three series into one row per day for the chart", () => {
    const rows = projectionRows({
      no_order: series(0, [90, 70, 50], 3),
      system: series(60, [90, 70, 110]),
      agent: series(40, [90, 70, 90]),
      storage_ceiling: 200,
    });
    expect(rows).toEqual([
      { day: 0, label: "Today", noOrder: 90, system: 90, agent: 90 },
      { day: 1, label: "D+1", noOrder: 70, system: 70, agent: 70 },
      { day: 2, label: "D+2", noOrder: 50, system: 110, agent: 90 },
    ]);
  });
  it("adds the buyer's line once they changed the quantity", () => {
    const rows = projectionRows({
      no_order: series(0, [90, 70], 2),
      system: series(60, [90, 70]),
      agent: series(40, [90, 70]),
      buyer: series(20, [90, 50]),
      storage_ceiling: null,
    });
    expect(rows.map((r) => r.buyer)).toEqual([90, 50]);
  });
  it("is empty without a projection", () => {
    expect(projectionRows(null)).toEqual([]);
  });
});
