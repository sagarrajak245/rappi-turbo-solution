"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { formatInr } from "@/lib/format";
import { Card, EmptyState, ErrorState, PageTitle, StatusBadge } from "@/components/ui";

export default function PurchaseOrdersPage() {
  const pos = useQuery({
    queryKey: ["purchase-orders"],
    queryFn: async () => unwrap(await api.GET("/purchase-orders")),
  });

  return (
    <>
      <PageTitle title="Purchase orders" subtitle="Orders the agent placed after your approval." />
      {pos.isLoading && <p className="text-neutral-500">Loading...</p>}
      {pos.isError && <ErrorState message={pos.error.message} onRetry={() => pos.refetch()} />}
      {pos.data?.length === 0 && (
        <EmptyState title="No orders yet" hint="Approve a proposal to place one." />
      )}
      {!!pos.data?.length && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-neutral-500">
              <tr>
                {["ERP number", "SKU", "Node", "Qty", "Total", "ETA", "ERP status", "Check", ""].map(
                  (h) => (
                    <th key={h} className="px-4 py-3 font-normal">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {pos.data.map((po) => (
                <tr key={po.erp_number} className="border-t border-neutral-200/70">
                  <td className="px-4 py-3 font-mono">{po.erp_number}</td>
                  <td className="px-4 py-3">{po.sku}</td>
                  <td className="px-4 py-3">{po.node}</td>
                  <td className="px-4 py-3">{po.qty}</td>
                  <td className="px-4 py-3">{formatInr(po.total_inr)}</td>
                  <td className="px-4 py-3">{po.eta}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={po.status} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={po.execution_status} />
                  </td>
                  <td className="px-4 py-3">
                    <Link href={`/runs/${po.run_id}`} className="underline">
                      Run
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
