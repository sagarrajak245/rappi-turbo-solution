import { describe, expect, it } from "vitest";
import { verdictStyle } from "./verdict";

describe("verdictStyle", () => {
  it("maps verdicts to a label and tone", () => {
    expect(verdictStyle("ACCEPT").tone).toBe("green");
    expect(verdictStyle("MODIFY").tone).toBe("yellow");
    expect(verdictStyle("REJECT").tone).toBe("coral");
    expect(verdictStyle("INVESTIGATE").tone).toBe("slate");
  });
  it("the backend's ESCALATE outcome overrides the verdict with a red outline", () => {
    const s = verdictStyle(null, "ESCALATE");
    expect(s.tone).toBe("red-outline");
    expect(s.label).toBe("Escalated");
  });
  it("a run with no verdict yet is neutral", () => {
    expect(verdictStyle(null)).toEqual({ label: "Pending", tone: "slate" });
  });
});
