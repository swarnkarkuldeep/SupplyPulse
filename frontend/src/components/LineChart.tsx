import { useEffect, useMemo, useRef, useState } from "react";
import { niceTicks } from "../lib/format";

export interface Pt {
  x: number;
  y: number | null;
  e?: number;
}
export interface Series {
  name?: string;
  color: string;
  dash?: string;
  width?: number;
  dots?: boolean;
  pts: Pt[];
}
export interface Band {
  name: string;
  color: string;
  pts: { x: number; lo: number; hi: number }[];
}

interface Props {
  label: string;
  series: Series[];
  bands?: Band[];
  vlines?: { x: number; label: string }[];
  hlines?: { y: number; label: string }[];
  yMin?: number;
  left?: number;
  yFmt: (v: number) => string;
  xFmt: (v: number) => string;
  tickFmt?: (v: number) => string;
  xTicks: (a: number, b: number) => number[];
  tip?: (s: Series, p: Pt) => string;
  legend?: boolean;
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export function LineChart(p: Props) {
  const [host, hostW] = useWidth();
  const [hover, setHover] = useState<number | null>(null);
  const W = Math.max(300, hostW - 16);
  const H = Math.round(Math.max(250, Math.min(380, W * 0.4)));
  const m = { l: p.left ?? 54, r: 16, t: 14, b: 30 };

  const g = useMemo(() => {
    const all: { x: number; y: number }[] = [];
    p.series.forEach((s) => s.pts.forEach((pt) => pt.y != null && all.push({ x: pt.x, y: pt.y })));
    (p.bands ?? []).forEach((b) => b.pts.forEach((pt) => all.push({ x: pt.x, y: pt.lo }, { x: pt.x, y: pt.hi })));
    const xMin = Math.min(...all.map((a) => a.x));
    const xMax = Math.max(...all.map((a) => a.x));
    let yMin = p.yMin ?? Math.min(...all.map((a) => a.y));
    let yMax = Math.max(...all.map((a) => a.y), ...(p.hlines ?? []).map((h) => h.y));
    yMax += (yMax - yMin) * 0.06;
    if (p.yMin == null) yMin -= (yMax - yMin) * 0.06;
    return { xMin, xMax, yMin, yMax };
  }, [p.series, p.bands, p.hlines, p.yMin]);

  const X = (v: number) => m.l + ((v - g.xMin) / (g.xMax - g.xMin || 1)) * (W - m.l - m.r);
  const Y = (v: number) => H - m.b - ((v - g.yMin) / (g.yMax - g.yMin || 1)) * (H - m.t - m.b);

  const xsSorted = useMemo(
    () => [...new Set(p.series.flatMap((s) => s.pts.filter((pt) => pt.y != null).map((pt) => pt.x)))].sort((a, b) => a - b),
    [p.series],
  );

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const x = g.xMin + ((px - m.l) / (W - m.l - m.r)) * (g.xMax - g.xMin);
    setHover(xsSorted.reduce((best, v) => (Math.abs(v - x) < Math.abs(best - x) ? v : best), xsSorted[0]));
  };

  const rows =
    hover == null
      ? []
      : p.series
          .map((s) => {
            const near = s.pts
              .filter((pt) => pt.y != null)
              .reduce<Pt | null>((b, pt) => (b == null || Math.abs(pt.x - hover) < Math.abs(b.x - hover) ? pt : b), null);
            return { s, pt: near };
          })
          .filter((r): r is { s: Series; pt: Pt } => r.pt != null && Math.abs(r.pt.x - hover) < (g.xMax - g.xMin) / 40);

  const tickFmt = p.tickFmt ?? p.xFmt;
  const vlineRight = (x: number) => X(x) > W * 0.6;

  return (
    <div className="chart" ref={host}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={p.label}>
        {niceTicks(g.yMin, g.yMax, 5).map((v) => (
          <g key={v}>
            <line className="tick-y" x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} />
            <text x={m.l - 8} y={Y(v) + 4} textAnchor="end">
              {p.yFmt(v)}
            </text>
          </g>
        ))}
        <line className="axis" x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} />
        {p.xTicks(g.xMin, g.xMax).map((v) => (
          <g key={v}>
            <line className="axis" x1={X(v)} x2={X(v)} y1={H - m.b} y2={H - m.b + 4} />
            <text x={X(v)} y={H - 8} textAnchor="middle">
              {tickFmt(v)}
            </text>
          </g>
        ))}
        {(p.bands ?? []).map((b) => (
          <polygon
            key={b.name}
            points={[...b.pts.map((q) => `${X(q.x)},${Y(q.hi)}`), ...[...b.pts].reverse().map((q) => `${X(q.x)},${Y(q.lo)}`)].join(" ")}
            fill={b.color}
            opacity={0.16}
          />
        ))}
        {(p.hlines ?? []).map((h) => (
          <g key={h.label}>
            <line x1={m.l} x2={W - m.r} y1={Y(h.y)} y2={Y(h.y)} stroke="#101a2c" strokeWidth={2} strokeDasharray="6 4" />
            <text x={W - m.r} y={Y(h.y) - 6} textAnchor="end" className="strong">
              {h.label}
            </text>
          </g>
        ))}
        {(p.vlines ?? []).map((v) => (
          <g key={v.label}>
            <line x1={X(v.x)} x2={X(v.x)} y1={m.t} y2={H - m.b} stroke="#101a2c" strokeWidth={1.5} strokeDasharray="3 3" />
            <text x={X(v.x) + (vlineRight(v.x) ? -6 : 6)} y={m.t + 12} textAnchor={vlineRight(v.x) ? "end" : "start"} className="strong">
              {v.label}
            </text>
          </g>
        ))}
        {p.series.map((s, i) => {
          let d = "";
          let pen = false;
          for (const pt of s.pts) {
            if (pt.y == null) {
              pen = false;
              continue;
            }
            d += `${pen ? "L" : "M"}${X(pt.x).toFixed(1)},${Y(pt.y).toFixed(1)}`;
            pen = true;
          }
          return (
            <g key={i}>
              <path d={d} fill="none" stroke={s.color} strokeWidth={s.width ?? 2.25} strokeDasharray={s.dash} strokeLinejoin="round" strokeLinecap="round" />
              {s.dots && s.pts.map((pt, j) => pt.y != null && <circle key={j} cx={X(pt.x)} cy={Y(pt.y)} r={4} fill={s.color} stroke="#f6f7f4" strokeWidth={1.5} />)}
            </g>
          );
        })}
        {hover != null && rows.length > 0 && (
          <g>
            <line x1={X(hover)} x2={X(hover)} y1={m.t} y2={H - m.b} stroke="#101a2c" strokeWidth={1} />
            {rows.map((r, i) => (
              <circle key={i} cx={X(r.pt.x)} cy={Y(r.pt.y!)} r={4.5} fill={r.s.color} stroke="#101a2c" strokeWidth={1.5} />
            ))}
          </g>
        )}
        <rect x={m.l} y={m.t} width={W - m.l - m.r} height={H - m.t - m.b} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hover != null && rows.length > 0 && (
        <div className="tip" style={{ left: Math.min(Math.max((X(hover) / W) * (hostW - 16), 80), hostW - 100) + 8, top: 8 }}>
          <b>{p.xFmt(hover)}</b>
          {rows.map((r, i) => (
            <div key={i}>
              <i style={{ background: r.s.color }} />
              {p.tip ? p.tip(r.s, r.pt) : `${r.s.name} ${p.yFmt(r.pt.y!)}`}
            </div>
          ))}
        </div>
      )}
      {p.legend !== false && (
        <div className="lg">
          {p.series
            .filter((s) => s.name)
            .map((s) => (
              <span key={s.name}>
                <i className="swatch" style={{ borderTop: `3px ${s.dash ? "dashed" : "solid"} ${s.color}` }} />
                {s.name}
              </span>
            ))}
          {(p.bands ?? []).map((b) => (
            <span key={b.name}>
              <i className="swatch band" style={{ background: b.color }} />
              {b.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
