import { describe, expect, it } from "vitest";
import { formatInr, pct } from "./format";

describe("formatInr", () => {
  it("formats decimal strings with Indian grouping and no paise", () => {
    expect(formatInr("123456.70")).toBe("₹1,23,457");
  });
});

describe("pct", () => {
  it("rounds used/limit to a whole percent", () => {
    expect(pct("250", 1000)).toBe(25);
  });
  it("clamps overspend to 100 and returns 0 without a limit", () => {
    expect(pct(1500, 1000)).toBe(100);
    expect(pct(10, 0)).toBe(0);
  });
});
