import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { LabelDisplay } from "@agent-console/contracts";
import { RunLabelChips } from "./RunLabelChips";
import { fillQuery, resolveLabelChips } from "./runLabels";

afterEach(cleanup);

// 라벨 키·역할·접두는 모두 임의 값이다. 웹은 규칙의 key만 비교한다.
const DISPLAY: LabelDisplay[] = [
  { key: "x.task", title: "작업", target: { role: "r-any", id_from: "x.spec", query: "tab=tasks&task={value}&s={labels.x.spec}" }, group: "g", order: 2 },
  { key: "x.spec", title: "스펙", target: { role: "r-any", id_from: "x.spec" }, group: "g", order: 1 },
  { key: "x.note", title: "메모", target: null },
];
const pathOf = (role: string) => (role === "r-any" ? "/any" : undefined);

describe("resolveLabelChips", () => {
  it("같은 그룹은 한 칩에 order 순으로 이어지고, 링크는 역할 경로 + id 라벨 + 질의 틀로 만든다", () => {
    const { chips, unmatched } = resolveLabelChips({ "x.spec": "sp 1", "x.task": "2.3" }, DISPLAY, pathOf);
    expect(unmatched).toEqual({});
    expect(chips).toHaveLength(1);
    expect(chips[0]?.segments.map((s) => [s.title, s.value, s.href])).toEqual([
      ["스펙", "sp 1", "/any/sp%201"],
      ["작업", "2.3", "/any/sp%201?tab=tasks&task=2.3&s=sp%201"],
    ]);
  });

  it("역할을 맡은 화면이 없거나 id 라벨이 없으면 링크 없는 칩이다. 규칙에 없는 라벨은 unmatched로 묶는다", () => {
    const a = resolveLabelChips({ "x.task": "1", other: "v" }, DISPLAY, pathOf);
    expect(a.chips[0]?.segments[0]?.href).toBeUndefined();
    expect(a.unmatched).toEqual({ other: "v" });
    const b = resolveLabelChips({ "x.spec": "s" }, DISPLAY, () => undefined);
    expect(b.chips[0]?.segments[0]?.href).toBeUndefined();
  });

  it("규칙이 없고 라벨만 있어도 unmatched에 모인다. 라벨이 없으면 비어 있다", () => {
    expect(resolveLabelChips({ a: "1" }, [], pathOf)).toEqual({ chips: [], unmatched: { a: "1" } });
    expect(resolveLabelChips(undefined, DISPLAY, pathOf)).toEqual({ chips: [], unmatched: {} });
  });

  it("fillQuery는 {value}·{labels.키}만 바꾸고 모르는 자리는 그대로 둔다", () => {
    expect(fillQuery("a={value}&b={labels.k}&c={labels.none}&d={x}", "v w", { k: "1" })).toBe("a=v%20w&b=1&c={labels.none}&d={x}");
  });
});

describe("RunLabelChips", () => {
  const view = (labels: Record<string, string>) =>
    render(<MemoryRouter><RunLabelChips model={resolveLabelChips(labels, DISPLAY, pathOf)} /></MemoryRouter>);

  it("라벨이 없으면 아무것도 그리지 않는다", () => {
    const { container } = view({});
    expect(container.textContent).toBe("");
  });

  it("그룹 칩은 링크이고 규칙에 없는 라벨은 `라벨 n` 팝오버로 묶인다", () => {
    view({ "x.spec": "s1", "x.task": "t1", z: "1", y: "2" });
    expect(screen.getByRole("link", { name: /스펙 s1/ }).getAttribute("href")).toBe("/any/s1");
    expect(screen.getByRole("button", { name: /라벨 2/ })).toBeTruthy();
  });
});
