"use client";

import { useEffect, useReducer, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api/client";
import { notificationsReducer, unreadCount, type Notif } from "@/lib/notifications";

export function NotificationBell() {
  const router = useRouter();
  const [items, dispatch] = useReducer(notificationsReducer, [] as Notif[]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let closed = false;
    api.GET("/notifications").then((res) => {
      if (!closed && res.data) dispatch({ type: "set", items: res.data });
    });
    const es = new EventSource("/api/notifications/stream");
    es.onmessage = (ev) => {
      try {
        const item = JSON.parse(ev.data) as Notif;
        dispatch({ type: "add", item });
        toast(item.message, {
          action: item.run_id
            ? { label: "Open", onClick: () => router.push(`/runs/${item.run_id}`) }
            : undefined,
        });
      } catch {
        /* ignore keep-alive / malformed frames */
      }
    };
    return () => {
      closed = true;
      es.close();
    };
  }, [router]);

  async function markRead(n: Notif) {
    if (!n.read_at) {
      dispatch({ type: "read", id: n.id, at: new Date().toISOString() });
      await api.POST("/notifications/{notification_id}/read", {
        params: { path: { notification_id: n.id } },
      });
    }
    setOpen(false);
    if (n.run_id) router.push(`/runs/${n.run_id}`);
  }

  const unread = unreadCount(items);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        className="relative rounded-full bg-white/80 p-2.5 shadow-sm"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-[#FF441F] px-1 text-[11px] text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 overflow-hidden rounded-[24px] bg-white shadow-[0_8px_30px_rgba(31,31,31,0.12)]">
          {items.length === 0 ? (
            <p className="p-4 text-sm text-neutral-500">You are all caught up.</p>
          ) : (
            <ul className="max-h-96 divide-y overflow-y-auto">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    onClick={() => markRead(n)}
                    className="flex w-full items-start gap-2 p-4 text-left text-sm hover:bg-neutral-50"
                  >
                    {!n.read_at && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#F5D547]" />}
                    <span className={n.read_at ? "text-neutral-500" : ""}>{n.message}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
