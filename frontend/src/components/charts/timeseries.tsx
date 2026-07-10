"use client";

import { useMemo, useRef, useState } from "react";

/**
 * Dependency-free SVG time-series charts in the Vantage voice.
 *
 * Dataviz method notes (see dataviz skill):
 * - Single series per chart → no legend; the panel title names it.
 * - Marks are thin (2px line / slim bars with 2px surface gaps, 4px
 *   rounded tops anchored to the baseline); grid & axes recessive.
 * - Hover layer by default: crosshair + tooltip (area), per-bar tooltip.
 * - Text wears ink tokens, never the series color.
 * - Series colors are brand signals validated for chroma + ≥3:1 contrast
 *   on the panel surface; a data table accompanies charts on the page.
 */

export interface SeriesPoint {
  label: string;
  value: number;
}

const W = 720;
const H = 220;
const PAD = { top: 12, right: 12, bottom: 26, left: 46 };
const IW = W - PAD.left - PAD.right;
const IH = H - PAD.top - PAD.bottom;

function niceTicks(max: number, count = 3): number[] {
  if (max <= 0) return [0];
  const step = Math.pow(10, Math.floor(Math.log10(max / count)));
  const err = max / count / step;
  const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const s = mult * step;
  const ticks: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += s) ticks.push(v);
  return ticks;
}

function compactNumber(n: number): string {
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

interface ChartBaseProps {
  points: SeriesPoint[];
  color: string;
  /**
   * Serializable format descriptor (charts are client components rendered
   * by server pages — functions can't cross the RSC boundary).
   * Omit for compact counts; pass a currency code for money.
   */
  currency?: string;
  ariaLabel: string;
}

function makeFormatter(currency?: string): (v: number) => string {
  if (!currency) return compactNumber;
  return (v) =>
    new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency,
      notation: v >= 10_000 ? "compact" : "standard",
      maximumFractionDigits: v >= 10_000 ? 1 : 0,
    }).format(v);
}

function useHover(count: number) {
  const ref = useRef<SVGSVGElement | null>(null);
  const [idx, setIdx] = useState<number | null>(null);
  function onMove(e: React.PointerEvent) {
    const svg = ref.current;
    if (!svg || count === 0) return;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W - PAD.left;
    const i = Math.round((x / IW) * (count - 1));
    setIdx(Math.max(0, Math.min(count - 1, i)));
  }
  return { ref, idx, setIdx, onMove };
}

function Tooltip({
  point,
  x,
  format,
}: {
  point: SeriesPoint;
  x: number;
  format: (v: number) => string;
}) {
  const flip = x > W * 0.62;
  return (
    <foreignObject
      x={flip ? x - 168 : x + 8}
      y={PAD.top}
      width={160}
      height={62}
      pointerEvents="none"
    >
      <div className="border-edge-strong bg-raised/95 rounded-lg border px-3 py-2 shadow-lg backdrop-blur">
        <p className="micro text-faint">{point.label}</p>
        <p className="text-ink font-mono text-sm">{format(point.value)}</p>
      </div>
    </foreignObject>
  );
}

function Grid({ ticks, max }: { ticks: number[]; max: number }) {
  return (
    <g aria-hidden>
      {ticks.map((t) => {
        const y = PAD.top + IH - (max === 0 ? 0 : (t / max) * IH);
        return (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="#262a33" strokeWidth={1} />
            <text
              x={PAD.left - 8}
              y={y + 3}
              textAnchor="end"
              fontSize={10}
              fill="#5a6071"
              fontFamily="var(--font-mono)"
            >
              {compactNumber(t)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function XLabels({ points }: { points: SeriesPoint[] }) {
  // First / middle / last — recessive, never a label per point
  const picks =
    points.length <= 2
      ? points.map((_, i) => i)
      : [0, Math.floor((points.length - 1) / 2), points.length - 1];
  return (
    <g aria-hidden>
      {picks.map((i) => {
        const x =
          points.length === 1 ? PAD.left + IW / 2 : PAD.left + (i / (points.length - 1)) * IW;
        return (
          <text
            key={i}
            x={x}
            y={H - 8}
            textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
            fontSize={10}
            fill="#5a6071"
            fontFamily="var(--font-mono)"
          >
            {points[i]?.label}
          </text>
        );
      })}
    </g>
  );
}

export function AreaTimeseries({ points, color, currency, ariaLabel }: ChartBaseProps) {
  const format = makeFormatter(currency);
  const { ref, idx, setIdx, onMove } = useHover(points.length);
  const max = useMemo(() => Math.max(...points.map((p) => p.value), 0), [points]);
  const ticks = useMemo(() => niceTicks(max), [max]);

  if (points.length === 0) {
    return <p className="text-muted px-2 py-10 text-center text-sm">No data in this window yet.</p>;
  }

  const xFor = (i: number) =>
    points.length === 1 ? PAD.left + IW / 2 : PAD.left + (i / (points.length - 1)) * IW;
  const yFor = (v: number) => PAD.top + IH - (max === 0 ? 0 : (v / max) * IH);

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i)},${yFor(p.value)}`).join(" ");
  const area = `${line} L${xFor(points.length - 1)},${PAD.top + IH} L${xFor(0)},${PAD.top + IH} Z`;
  const gid = `area-${color.replace("#", "")}`;

  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={ariaLabel}
      className="w-full"
      onPointerMove={onMove}
      onPointerLeave={() => setIdx(null)}
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.28} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <Grid ticks={ticks} max={max} />
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
      {/* last point marker + selective direct label */}
      <circle cx={xFor(points.length - 1)} cy={yFor(points.at(-1)!.value)} r={4} fill={color} />
      <text
        x={Math.min(xFor(points.length - 1), W - PAD.right - 4)}
        y={yFor(points.at(-1)!.value) - 10}
        textAnchor="end"
        fontSize={11}
        fill="#eaedf2"
        fontFamily="var(--font-mono)"
      >
        {format(points.at(-1)!.value)}
      </text>
      <XLabels points={points} />
      {idx !== null && points[idx] ? (
        <g>
          <line
            x1={xFor(idx)}
            x2={xFor(idx)}
            y1={PAD.top}
            y2={PAD.top + IH}
            stroke="#3a4250"
            strokeWidth={1}
          />
          <circle
            cx={xFor(idx)}
            cy={yFor(points[idx].value)}
            r={5}
            fill={color}
            stroke="#121419"
            strokeWidth={2}
          />
          <Tooltip point={points[idx]} x={xFor(idx)} format={format} />
        </g>
      ) : null}
    </svg>
  );
}

export function BarTimeseries({ points, color, currency, ariaLabel }: ChartBaseProps) {
  const format = makeFormatter(currency);
  const { ref, idx, setIdx, onMove } = useHover(points.length);
  const max = useMemo(() => Math.max(...points.map((p) => p.value), 0), [points]);
  const ticks = useMemo(() => niceTicks(max), [max]);

  if (points.length === 0) {
    return <p className="text-muted px-2 py-10 text-center text-sm">No data in this window yet.</p>;
  }

  const slot = IW / points.length;
  const barW = Math.max(3, Math.min(28, slot - 2)); // ≥2px surface gap between bars

  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={ariaLabel}
      className="w-full"
      onPointerMove={onMove}
      onPointerLeave={() => setIdx(null)}
    >
      <Grid ticks={ticks} max={max} />
      {points.map((p, i) => {
        const h = max === 0 ? 0 : (p.value / max) * IH;
        const x = PAD.left + i * slot + (slot - barW) / 2;
        const y = PAD.top + IH - h;
        return (
          <g key={p.label}>
            {/* rounded top, flat baseline: clip a rounded rect at the baseline */}
            <path
              d={`M${x},${y + Math.min(4, h)} q0,-4 4,-4 h${barW - 8} q4,0 4,4 v${Math.max(0, h - Math.min(4, h))} h${-barW} Z`}
              fill={color}
              opacity={idx === null || idx === i ? 1 : 0.45}
            />
          </g>
        );
      })}
      <XLabels points={points} />
      {idx !== null && points[idx] ? (
        <Tooltip point={points[idx]} x={PAD.left + idx * slot + slot / 2} format={format} />
      ) : null}
    </svg>
  );
}
