"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { projectionRows, type StockProjection } from "@/lib/projection";

/** 14-day stock: no order vs the system's qty vs the agent's qty, with stockout and storage ceiling. */
export function ProjectionChart({ projection }: { projection: StockProjection }) {
  const rows = projectionRows(projection);
  const stockout = projection.no_order.stockout_day;
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#e5e5e5" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} width={50} />
          <Tooltip />
          <Legend />
          <Line
            name="No order"
            dataKey="noOrder"
            stroke="#FF441F"
            strokeDasharray="5 4"
            dot={false}
          />
          <Line
            name={`System (${projection.system.qty})`}
            dataKey="system"
            stroke="#a3a3a3"
            dot={false}
          />
          <Line
            name={`Agent (${projection.agent.qty})`}
            dataKey="agent"
            stroke="#1F1F1F"
            strokeWidth={2.5}
            dot={false}
          />
          {stockout !== null && (
            <ReferenceLine
              x={rows[stockout]?.label}
              stroke="#FF441F"
              label={{ value: "Stockout", fontSize: 11, fill: "#C2300F", position: "top" }}
            />
          )}
          {projection.storage_ceiling !== null && (
            <ReferenceLine
              y={projection.storage_ceiling}
              stroke="#F5D547"
              strokeWidth={2}
              label={{ value: "Storage ceiling", fontSize: 11, position: "insideTopRight" }}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
