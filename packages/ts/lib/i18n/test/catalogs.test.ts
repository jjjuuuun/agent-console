import { describe, expect, test } from "vitest";

import { compareCatalogs, formatNamesOf, placeholdersOf } from "@agent-console/i18n";
import { assertCatalogsMatch } from "@agent-console/i18n/testing";

describe("compareCatalogs", () => {
  test("same keys and placeholders, any order", () => {
    const ko = { a: { b: "{x}과 {y}" }, c: "끝" };
    const en = { a: { b: "{y} and {x}" }, c: "end" };
    expect(compareCatalogs(ko, en).same).toBe(true);
  });
  test("reports missing keys and placeholder differences", () => {
    const diff = compareCatalogs({ a: "{x}", only: "k" }, { a: "{y}", extra: "e" });
    expect(diff.onlyInA).toEqual(["only"]);
    expect(diff.onlyInB).toEqual(["extra"]);
    expect(diff.placeholderMismatches).toEqual([{ key: "a", a: ["x"], b: ["y"] }]);
  });
  test("plural forms are compared as one key", () => {
    const ko = { issues_other: "{count}개" };
    const en = { issues_one: "{count} issue", issues_other: "{count} issues" };
    expect(compareCatalogs(ko, en).same).toBe(true);
    expect(compareCatalogs({ n_one: "one thing", n_other: "{count} things" }, { n_other: "{count}" }).same).toBe(true);
  });
  test("format names are not placeholders", () => {
    expect(placeholdersOf("{label, particle.object} {n, number(maximumFractionDigits: 1)}")).toEqual(["label", "n"]);
    expect(formatNamesOf("{label, particle.object} {n, number(maximumFractionDigits: 1)} {z}")).toEqual(["number", "particle.object"]);
  });
});

describe("assertCatalogsMatch", () => {
  test("passes for matching catalogs", () => {
    expect(() => assertCatalogsMatch({ a: "{x}" }, { a: "{x}" })).not.toThrow();
  });
  test("fails with a report", () => {
    expect(() => assertCatalogsMatch({ a: "{x}", b: "1" }, { a: "{y}" })).toThrow(/only in first: b[\s\S]*placeholders differ at a/);
  });
  test("a particle format in the second catalog (English) fails", () => {
    expect(() => assertCatalogsMatch({ a: "{x, particle.object}" }, { a: "{x, particle.object}" })).toThrow(/particle\./);
  });
});
