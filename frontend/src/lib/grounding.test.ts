import { describe, expect, it } from "vitest";
import { data } from "../data";
import { allowedYears, checkLine, parseBlocks, tamper } from "./grounding";

describe("review pack number check", () => {
  for (const pack of data.packs) {
    it(`accepts every number in the real ${pack.period} pack (${pack.validation.mode})`, () => {
      const years = allowedYears(pack.facts);
      const unsupported = parseBlocks(pack.markdown)
        .filter((b) => b.kind !== "h")
        .flatMap((b) => checkLine(b.text, pack.facts, years).filter((r) => !r.ok).map((r) => r.raw));
      expect(unsupported).toEqual([]);
    });

    it(`rejects a changed number in the ${pack.period} pack`, () => {
      const years = allowedYears(pack.facts);
      const blocks = parseBlocks(pack.markdown);
      const t = tamper(blocks, pack.facts, years);
      expect(t).not.toBeNull();
      expect(checkLine(t!.text, pack.facts, years).some((r) => !r.ok)).toBe(true);
    });
  }

  it("counts the same numbers as the Python validator logged for the LLM pack", () => {
    const pack = data.packs.find((p) => p.validation.mode === "llm");
    if (!pack) return;
    const years = allowedYears(pack.facts);
    const n = parseBlocks(pack.markdown)
      .filter((b) => b.kind !== "h")
      .flatMap((b) => checkLine(b.text, pack.facts, years))
      .filter((r) => !r.isYear).length;
    const passing = pack.validation.attempts.filter((a) => a.ok).pop();
    expect(n).toBe(passing?.numbers_checked);
  });

  it("treats a four-digit number as a year only when a fact's period names it", () => {
    const facts = [{ id: "F1", metric: "Orders", value: 2037, period: "2018-01", source_query: "q" }];
    expect(checkLine("2,037 orders [F1]", facts, allowedYears(facts))[0].ok).toBe(true);
    expect(checkLine("in 2019 [F1]", facts, allowedYears(facts))[0].ok).toBe(false);
    expect(checkLine("in 2018 [F1]", facts, allowedYears(facts))[0].ok).toBe(true);
  });

  it("only accepts a number backed by a fact cited on the same line", () => {
    const facts = [
      { id: "F1", metric: "A", value: 10, period: "2018-01", source_query: "q" },
      { id: "F2", metric: "B", value: 99, period: "2018-01", source_query: "q" },
    ];
    expect(checkLine("A is 99 [F1]", facts, allowedYears(facts))[0].ok).toBe(false);
    expect(checkLine("A is 10 [F1]", facts, allowedYears(facts))[0].ok).toBe(true);
  });
});
