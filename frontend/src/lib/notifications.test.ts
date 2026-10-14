import { describe, expect, it } from "vitest";
import { notificationsReducer, unreadCount, type Notif } from "./notifications";

const n = (id: number, read_at: string | null = null): Notif => ({
  id,
  user_id: 1,
  kind: "run_ready",
  run_id: "r1",
  message: "m",
  read_at,
  created_at: "2026-01-01T00:00:00Z",
});

describe("notificationsReducer", () => {
  it("adds newest first and de-duplicates by id", () => {
    let s = notificationsReducer([], { type: "add", item: n(1) });
    s = notificationsReducer(s, { type: "add", item: n(2) });
    s = notificationsReducer(s, { type: "add", item: n(2) });
    expect(s.map((x) => x.id)).toEqual([2, 1]);
  });
  it("marks read and counts unread", () => {
    const s = notificationsReducer([n(2), n(1)], { type: "read", id: 2, at: "now" });
    expect(unreadCount(s)).toBe(1);
  });
});
