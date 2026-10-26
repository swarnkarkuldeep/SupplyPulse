// The review-pack number check, in the browser. It follows the rule in src/sca/grounding.py:
// every number on a line must equal (to the decimals written) a value, comparison value or change
// from a fact cited on that line. A bare four-digit number is a year only if a fact's period names it.
import type { Fact } from "../data";

export const CITE = /\[(F\d+)\]/g;
const NUM = /(?<![A-Za-z0-9])\$?[-−]?\d[\d,]*(?:\.\d+)?%?/g;

export interface Block {
  kind: "h" | "p" | "li";
  ordered?: boolean;
  text: string;
}

export interface NumberCheck {
  raw: string;
  index: number;
  ok: boolean;
  isYear: boolean;
  fact: Fact | null;
}

export type Part =
  | { kind: "text"; text: string; bold: boolean }
  | { kind: "cite"; id: string }
  | { kind: "num"; text: string; ok: boolean; fact: Fact | null };

export function parseBlocks(md: string): Block[] {
  const out: Block[] = [];
  for (const line of md.split(/\r?\n/)) {
    if (/^---\s*$/.test(line)) break;
    if (/^# /.test(line) || !line.trim()) continue;
    if (/^## /.test(line)) out.push({ kind: "h", text: line.slice(3).trim() });
    else if (/^\s*(?:[-*+]\s+)?\d+[.)]\s+/.test(line))
      out.push({ kind: "li", ordered: true, text: line.replace(/^\s*(?:[-*+]\s+)?\d+[.)]\s+/, "") });
    else if (/^\s*[-*+]\s+/.test(line)) out.push({ kind: "li", text: line.replace(/^\s*[-*+]\s+/, "") });
    else out.push({ kind: "p", text: line.trim() });
  }
  return out;
}

export function allowedYears(facts: Fact[]): Set<string> {
  const years = new Set<string>();
  for (const f of facts)
    for (const s of [f.period, f.comparison_period])
      for (const y of String(s ?? "").match(/\d{4}/g) ?? []) years.add(y);
  return years;
}

const cleanToken = (raw: string) => raw.replace(/[$,%]/g, "").replace("−", "-");

export function checkLine(text: string, facts: Fact[], years: Set<string>): NumberCheck[] {
  const cited = [...text.matchAll(CITE)].map((m) => m[1]);
  const pool = facts.filter((f) => cited.includes(f.id));
  const stripped = text.replace(CITE, " ");
  const results: NumberCheck[] = [];
  for (const m of stripped.matchAll(NUM)) {
    const raw = m[0];
    const tok = cleanToken(raw);
    const val = parseFloat(tok);
    const dec = (tok.split(".")[1] ?? "").length;
    const isYear = years.has(tok);
    let ok = isYear;
    let fact: Fact | null = null;
    if (!isYear) {
      for (const f of pool) {
        const cands = [f.value, f.comparison_value, f.delta].filter((v): v is number => typeof v === "number");
        if (cands.some((c) => Math.abs(+c.toFixed(dec) - val) < 1e-9 || Math.abs(+Math.abs(c).toFixed(dec) - Math.abs(val)) < 1e-9)) {
          ok = true;
          fact = f;
          break;
        }
      }
    }
    results.push({ raw, index: m.index ?? 0, ok, isYear, fact });
  }
  return results;
}

/** Split a line into plain text, citations and checked numbers, in reading order, for rendering. */
export function tokenize(text: string, facts: Fact[], years: Set<string>): Part[] {
  const checks = checkLine(text, facts, years);
  const used = new Set<NumberCheck>();
  const parts: Part[] = [];
  for (const seg of text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean)) {
    const bold = /^\*\*/.test(seg);
    const body = bold ? seg.slice(2, -2) : seg;
    let last = 0;
    for (const t of body.matchAll(new RegExp(CITE.source + "|" + NUM.source, "g"))) {
      const at = t.index ?? 0;
      if (at > last) parts.push({ kind: "text", text: body.slice(last, at), bold });
      last = at + t[0].length;
      if (t[1]) {
        parts.push({ kind: "cite", id: t[1] });
        continue;
      }
      const check = checks.find((c) => c.raw === t[0] && !used.has(c));
      if (check) used.add(check);
      if (!check || check.isYear) parts.push({ kind: "text", text: t[0], bold });
      else parts.push({ kind: "num", text: t[0], ok: check.ok, fact: check.fact });
    }
    if (last < body.length) parts.push({ kind: "text", text: body.slice(last), bold });
  }
  return parts;
}

export interface Tamper {
  block: number;
  text: string;
  fake: string;
}

/** Replace the first checkable number on the first cited line with a different one the cited facts do not support. */
export function tamper(blocks: Block[], facts: Fact[], years: Set<string>): Tamper | null {
  for (let bi = 0; bi < blocks.length; bi++) {
    const b = blocks[bi];
    if (b.kind === "h" || !/\[F\d+\]/.test(b.text)) continue;
    const target = checkLine(b.text, facts, years).find((r) => !r.isYear);
    if (!target) continue;
    const tok = cleanToken(target.raw);
    const dec = (tok.split(".")[1] ?? "").length;
    for (const k of [1.18, 1.37, 0.71]) {
      const num = parseFloat(tok) * k;
      const fake =
        (target.raw.startsWith("$") ? "$" : "") +
        num.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) +
        (target.raw.endsWith("%") ? "%" : "");
      const text = b.text.slice(0, target.index) + fake + b.text.slice(target.index + target.raw.length);
      if (checkLine(text, facts, years).some((r) => !r.ok)) return { block: bi, text, fake };
    }
  }
  return null;
}
