export interface BarItem {
  label: string;
  sub?: string;
  value: number;
  shown: string;
  cls?: "late" | "ok" | "hi";
  min?: number;
  max?: number;
}

export function Bars({ rows }: { rows: BarItem[] }) {
  return (
    <div className="bars">
      {rows.map((r) => {
        const min = r.min ?? 0;
        const max = r.max ?? 1;
        const w = Math.max(0, Math.min(100, ((r.value - min) / (max - min)) * 100));
        return (
          <div className="bar-row" key={r.label}>
            <div className="bar-label">
              {r.label}
              {r.sub && <small>{r.sub}</small>}
            </div>
            <div className="bar-track" role="img" aria-label={`${r.label}: ${r.shown}`}>
              <div className={`bar-fill ${r.cls ?? ""}`} style={{ width: `${w}%` }} />
            </div>
            <div className="bar-val">{r.shown}</div>
          </div>
        );
      })}
    </div>
  );
}
