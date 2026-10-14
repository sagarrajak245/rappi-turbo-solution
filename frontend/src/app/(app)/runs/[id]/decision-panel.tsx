"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { snapToCasePack } from "@/lib/casepack";
import { formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui";

type Run = Schemas["RunOut"];
type Proposal = Schemas["ProposalOut"];
type Decision = Schemas["HumanDecision"];

const REJECT_CHIPS = ["Stock is enough", "Demand looks inflated", "Supplier issue", "Promo ended"];

export function DecisionPanel({ run, proposal }: { run: Run; proposal: Proposal }) {
  const qc = useQueryClient();
  const pack = Number(proposal.facts.case_pack ?? 1);
  const unitCost = Number(proposal.facts.unit_cost_inr ?? 0);
  const [mode, setMode] = useState<"idle" | "modify" | "reject">("idle");
  const [qty, setQty] = useState(proposal.qty ?? 0);
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState<Decision | null>(null);

  const send = useMutation({
    mutationFn: async (body: Decision) =>
      unwrap(
        await api.POST("/agent/runs/{run_id}/decision", {
          params: { path: { run_id: run.id } },
          body,
        }),
      ),
    onSuccess: (out) => {
      setConfirm(null);
      // An invalid modify comes back 200, still awaiting approval, with the reason in `error`.
      if (out.status === "awaiting_approval" && out.error) toast.error(out.error);
      else toast.success(`Decision recorded: ${out.status.replaceAll("_", " ")}`);
      qc.setQueryData(["run", run.id], out);
      qc.invalidateQueries({ queryKey: ["lessons"] });
      qc.invalidateQueries({ queryKey: ["inbox"] });
    },
    onError: (e: Error) => {
      setConfirm(null);
      toast.error(e.message);
      qc.invalidateQueries({ queryKey: ["run", run.id] });
    },
  });

  if (proposal.outcome === "ESCALATE") {
    return (
      <Card>
        <p className="mb-4 text-sm text-neutral-600">
          The agent could not find a valid order. Pick a resolution above outside the app, then
          acknowledge so the item leaves your queue.
        </p>
        <button
          disabled={send.isPending}
          onClick={() => send.mutate({ action: "acknowledge" })}
          className="rounded-full bg-[#1F1F1F] px-5 py-2.5 text-sm text-white disabled:opacity-50"
        >
          Acknowledge
        </button>
      </Card>
    );
  }

  // Approving a no-order verdict (reject, investigate) only acknowledges it; no PO is placed.
  const placesOrder = proposal.valid && proposal.outcome === "PROPOSE" && !!proposal.qty;
  const snap = snapToCasePack(qty, pack);
  const deviates = qty !== proposal.qty;
  const canModify = snap.valid && deviates && reason.trim().length > 0;

  return (
    <Card>
      <div className="flex flex-wrap gap-3">
        <button
          disabled={send.isPending}
          onClick={() => (placesOrder ? setConfirm({ action: "approve" }) : send.mutate({ action: "approve" }))}
          className="rounded-full bg-[#1F1F1F] px-5 py-2.5 text-sm text-white disabled:opacity-50"
        >
          {placesOrder ? `Approve ${proposal.qty}` : "Agree, don't order"}
        </button>
        <button
          onClick={() => setMode(mode === "modify" ? "idle" : "modify")}
          className={cn("rounded-full px-5 py-2.5 text-sm", mode === "modify" ? "bg-[#F5D547]" : "bg-neutral-200")}
        >
          Change qty
        </button>
        <button
          onClick={() => setMode(mode === "reject" ? "idle" : "reject")}
          className={cn("rounded-full px-5 py-2.5 text-sm", mode === "reject" ? "bg-[#FF441F] text-white" : "bg-neutral-200")}
        >
          Reject
        </button>
      </div>

      {mode === "modify" && (
        <div className="mt-5 space-y-3">
          <label className="block text-sm">
            Quantity (case pack {pack})
            <input
              type="number"
              min={0}
              step={pack}
              value={qty}
              onChange={(e) => setQty(Number(e.target.value))}
              className="mt-1 block w-40 rounded-xl bg-white px-3 py-2"
            />
          </label>
          {!snap.valid && (
            <p className="text-sm">
              Not a whole case. Try{" "}
              {snap.suggestions.map((s) => (
                <button key={s} onClick={() => setQty(s)} className="mr-2 rounded-full bg-[#F5D547] px-3 py-1">
                  {s}
                </button>
              ))}
            </p>
          )}
          <ReasonInput value={reason} onChange={setReason} placeholder="Why this quantity? The agent learns from it." />
          <button
            disabled={!canModify || send.isPending}
            onClick={() => setConfirm({ action: "modify", qty, reason: reason.trim() })}
            className="rounded-full bg-[#1F1F1F] px-5 py-2.5 text-sm text-white disabled:opacity-50"
          >
            Review order
          </button>
        </div>
      )}

      {mode === "reject" && (
        <div className="mt-5 space-y-3">
          <div className="flex flex-wrap gap-2">
            {REJECT_CHIPS.map((c) => (
              <button key={c} onClick={() => setReason(c)} className="rounded-full bg-neutral-200 px-3 py-1 text-sm">
                {c}
              </button>
            ))}
          </div>
          <ReasonInput value={reason} onChange={setReason} placeholder="What did the agent miss?" />
          <button
            disabled={send.isPending}
            onClick={() => send.mutate({ action: "reject", reason: reason.trim() || null })}
            className="rounded-full bg-[#FF441F] px-5 py-2.5 text-sm text-white disabled:opacity-50"
          >
            Reject proposal
          </button>
        </div>
      )}

      {confirm && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-md bg-white">
            <h3 className="mb-4 text-lg">Place this purchase order?</h3>
            {(() => {
              const q = confirm.qty ?? proposal.qty ?? 0;
              return (
                <dl className="mb-6 grid grid-cols-2 gap-y-2 text-sm">
                  <dt className="text-neutral-500">SKU</dt>
                  <dd>{run.sku}</dd>
                  <dt className="text-neutral-500">Node</dt>
                  <dd>{run.node}</dd>
                  <dt className="text-neutral-500">Quantity</dt>
                  <dd>
                    {q} ({q / pack} cases)
                  </dd>
                  <dt className="text-neutral-500">Unit cost</dt>
                  <dd>{formatInr(unitCost)}</dd>
                  <dt className="text-neutral-500">Total</dt>
                  <dd className="font-medium">{formatInr(q * unitCost)}</dd>
                  {confirm.reason && (
                    <>
                      <dt className="text-neutral-500">Reason</dt>
                      <dd>{confirm.reason}</dd>
                    </>
                  )}
                </dl>
              );
            })()}
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirm(null)} className="rounded-full bg-neutral-200 px-5 py-2.5 text-sm">
                Cancel
              </button>
              <button
                disabled={send.isPending}
                onClick={() => send.mutate(confirm)}
                className="rounded-full bg-[#1F1F1F] px-5 py-2.5 text-sm text-white disabled:opacity-50"
              >
                {send.isPending ? "Placing…" : "Confirm and place"}
              </button>
            </div>
          </Card>
        </div>
      )}
    </Card>
  );
}

function ReasonInput(props: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <textarea
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
      placeholder={props.placeholder}
      rows={2}
      maxLength={500}
      className="block w-full rounded-xl bg-white px-3 py-2 text-sm"
    />
  );
}
