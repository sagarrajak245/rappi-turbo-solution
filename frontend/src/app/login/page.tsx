"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api/client";
import { Card } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await api.POST("/auth/login", { body: { email, password } });
    setBusy(false);
    if (res.error !== undefined) {
      setError(errorMessage(res.error, "Could not sign in. Check your email and password."));
      return;
    }
    qc.clear();
    router.replace("/");
    router.refresh();
  }

  const input = "w-full rounded-full border border-neutral-200 bg-white px-4 py-3 outline-none focus:ring-2 focus:ring-[#F5D547]";

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <h1 className="text-2xl font-light">Welcome back</h1>
        <p className="mb-6 mt-1 text-sm text-neutral-500">Sign in to see what needs your decision.</p>
        <form onSubmit={onSubmit} className="space-y-3">
          <input
            className={input}
            type="email"
            placeholder="Email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            className={input}
            type="password"
            placeholder="Password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p className="text-sm text-[#C2300F]">{error}</p>}
          <button
            disabled={busy}
            className="w-full rounded-full bg-[#1F1F1F] py-3 text-white disabled:opacity-60"
          >
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </Card>
    </main>
  );
}
