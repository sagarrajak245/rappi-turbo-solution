import { describe, expect, it } from "vitest";
import { decisionFormKey } from "./decision";

describe("decisionFormKey", () => {
  it("changes when the agent re-plans, so the old qty and reason are cleared", () => {
    const before = decisionFormKey({ id: "r1", replans_done: 0 });
    expect(decisionFormKey({ id: "r1", replans_done: 1 })).not.toBe(before);
  });

  it("stays the same within one proposal, so a rejected modify keeps the buyer's input", () => {
    expect(decisionFormKey({ id: "r1", replans_done: 1 })).toBe(decisionFormKey({ id: "r1", replans_done: 1 }));
    expect(decisionFormKey({ id: "r2", replans_done: 1 })).not.toBe(decisionFormKey({ id: "r1", replans_done: 1 }));
  });
});
