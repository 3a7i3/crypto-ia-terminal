// ── Sparkline.tsx — SVG inline léger, zéro dépendance ────────────────────────

import React, { useMemo } from "react";
import { pnlColor } from "../lib/tokens";

interface Props {
  data: number[];
  width?: number;
  height?: number;
  strokeWidth?: number;
  showArea?: boolean;
  className?: string;
}

export const Sparkline: React.FC<Props> = ({
  data,
  width = 80,
  height = 24,
  strokeWidth = 1.5,
  showArea = false,
  className = "",
}) => {
  const { linePath, areaPath, color } = useMemo(() => {
    if (!data || data.length < 2)
      return { linePath: null, areaPath: null, color: "var(--neutral)" };

    const min = Math.min(...data);
    const max = Math.max(...data);
    const rng = max - min || 1;
    const px  = strokeWidth;
    const W   = width  - px * 2;
    const H   = height - px * 2;

    const pts = data.map((v, i) => ({
      x: px + (i / (data.length - 1)) * W,
      y: px + (1 - (v - min) / rng) * H,
    }));

    const line = "M" + pts.map(p => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" L");
    const area = line +
      ` L${pts.at(-1)!.x.toFixed(2)},${(height - px).toFixed(2)}` +
      ` L${pts[0].x.toFixed(2)},${(height - px).toFixed(2)} Z`;

    return {
      linePath: line,
      areaPath: area,
      color: pnlColor((data.at(-1) ?? 0) - (data[0] ?? 0)),
    };
  }, [data, width, height, strokeWidth]);

  if (!linePath) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
      style={{ display: "block", overflow: "visible" }}
    >
      {showArea && <path d={areaPath!} fill={color} opacity={0.08} />}
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
};
