"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { api } from "@/lib/api/client";
import { useMe } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { NotificationBell } from "./notification-bell";

interface NavItem {
  href: string;
  label: string;
  soon?: boolean;
  admin?: boolean;
}

const NAV: NavItem[] = [
  { href: "/", label: "Home" },
  { href: "/inbox", label: "Inbox" },
  { href: "/purchase-orders", label: "Purchase orders" },
  { href: "/memory", label: "Memory" },
  { href: "/change-requests", label: "Change requests", soon: true },
  { href: "/admin", label: "Admin", admin: true },
  { href: "/evaluation", label: "Evaluation", admin: true },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [menu, setMenu] = useState(false);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const items = NAV.filter((n) => !n.admin || me?.role === "admin");

  async function logout() {
    await api.POST("/auth/logout");
    qc.clear();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <header className="mb-8 flex items-center justify-between gap-4">
        <nav className="flex flex-wrap gap-1 rounded-full bg-white/70 p-1.5 shadow-sm backdrop-blur-md">
          {items.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "rounded-full px-4 py-2 text-sm transition-colors",
                isActive(n.href) ? "bg-black text-white" : "text-neutral-600 hover:bg-white",
              )}
            >
              {n.label}
              {n.soon && <span className="ml-1.5 text-[10px] uppercase opacity-60">soon</span>}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <NotificationBell />
          <div className="relative">
            <button
              onClick={() => setMenu((m) => !m)}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-[#F5D547] font-medium"
              aria-label="User menu"
            >
              {me?.name?.[0]?.toUpperCase() ?? "?"}
            </button>
            {menu && (
              <div className="absolute right-0 z-20 mt-2 w-56 rounded-[24px] bg-white p-4 shadow-[0_8px_30px_rgba(31,31,31,0.12)]">
                <p className="font-medium">{me?.name}</p>
                <p className="text-xs text-neutral-500">{me?.email}</p>
                <p className="mb-3 text-xs capitalize text-neutral-400">
                  {me?.role} {me?.branch ? `- ${me.branch}` : ""}
                </p>
                <button onClick={logout} className="flex items-center gap-2 text-sm text-[#C2300F]">
                  <LogOut className="h-4 w-4" /> Log out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
