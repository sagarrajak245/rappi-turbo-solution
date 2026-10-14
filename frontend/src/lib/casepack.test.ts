import { describe, expect, it } from "vitest";
import { snapToCasePack } from "./casepack";

describe("snapToCasePack", () => {
  it("suggests the nearest valid multiples around an invalid qty", () => {
    expect(snapToCasePack(800, 48)).toEqual({ valid: false, suggestions: [768, 816] });
  });
  it("accepts exact multiples", () => {
    expect(snapToCasePack(96, 48)).toEqual({ valid: true, suggestions: [96] });
  });
  it("never suggests below one pack", () => {
    expect(snapToCasePack(10, 48).suggestions).toEqual([48]);
  });
});
