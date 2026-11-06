import { describe, expect, it } from "vitest";
import type { DelegationStrategyDescriptor } from "@agent-console/contracts";
import { attributeRows, attributeSummary, edgeSessionOf, hasAttributes, sessionOf, sessionText, sessionTip, sessionChipView } from "./index";

/** 임의 이름·임의 값의 방식. 화면은 속성만 본다(R0). */
const strat = (over: Partial<DelegationStrategyDescriptor> = {}) => ({ id: "q-1", title: "임의 방식", member_fields: [], max_depth: 1, ...over }) as DelegationStrategyDescriptor;

describe("위임 방식 속성 어댑터(5.7R.34)", () => {
  it("행 순서는 세션 → 깊이 → 백엔드 → 중첩이고 값이 없는 속성은 행이 없다", () => {
    const rows = attributeRows(strat({ session: "same", max_depth: 1, backend: "delegator", nestable: false }), "리더");
    expect(rows.map((r) => r.key)).toEqual(["session", "max_depth", "backend", "nestable"]);
    expect(rows[0]!.long).toBe("리더 세션 안에서 실행됩니다");
    expect(rows[1]!.long).toBe("1단계 — 대상은 다시 위임할 수 없습니다");
    expect(attributeRows(strat({ max_depth: undefined as never })).map((r) => r.key)).toEqual([]);
    expect(attributeRows(strat({ session: "separate", max_depth: undefined as never, nestable: true })).map((r) => r.key)).toEqual(["session", "nestable"]);
  });
  it("알 수 없는 값은 원문(mono 표시용)이고 빈 방식·undefined는 행이 없다", () => {
    const [row] = attributeRows(strat({ session: "x1", max_depth: undefined as never }));
    expect(row).toMatchObject({ key: "session", raw: "x1", long: "x1", short: "x1", unknownValue: true });
    expect(attributeRows(undefined)).toEqual([]);
    expect(hasAttributes(strat({ max_depth: undefined as never }))).toBe(false);
  });
  it("깊이: null은 제한 없음, 2 이상은 n단계까지", () => {
    expect(attributeRows(strat({ max_depth: null }))[0]).toMatchObject({ long: "제한 없음(설정 ‘위임 깊이’ 한도까지)", short: "깊이 제한 없음" });
    expect(attributeRows(strat({ max_depth: 3 }))[0]).toMatchObject({ long: "3단계까지", short: "깊이 3" });
  });
  it("옵션 보조 줄 요약은 짧은 문구를 순서대로 · 로 잇고 중첩 불가는 생략한다", () => {
    expect(attributeSummary(strat({ session: "same", max_depth: 1, backend: "delegator", nestable: false }))).toBe("같은 세션 · 깊이 1 · 위임자 백엔드");
    expect(attributeSummary(strat({ session: "separate", max_depth: null, backend: "target", nestable: true }))).toBe("별도 세션 · 깊이 제한 없음 · 대상 백엔드 · 중첩 가능");
  });
  it("연결의 세션: 위임 연결은 유효 방식의 값, 그 밖은 종류 값, 방식을 모르면 없음", () => {
    const list = [{ id: "q-1", session: "same" }, { id: "q-2", session: "x9" }, { id: "q-3" }];
    const kind = { invocation: { strategy: "q-1" } } as never;
    expect(edgeSessionOf({}, kind, list)).toBe("same");
    expect(edgeSessionOf({ config: { strategy: "q-2" } }, kind, list)).toBe("x9");
    expect(edgeSessionOf({ config: { strategy: "q-3" } }, kind, list)).toBeUndefined();
    expect(edgeSessionOf({ config: { strategy: "ghost" } }, kind, list)).toBeUndefined();
    expect(edgeSessionOf({}, { session: "separate" } as never, list)).toBe("separate");
    expect(edgeSessionOf({}, { session: null } as never, list)).toBeUndefined();
    expect(edgeSessionOf({}, undefined, list)).toBeUndefined();
    expect(sessionOf(strat({ session: "" }))).toBeUndefined();
  });
  it("세션 칩 문구·툴팁·편집기 칩 데이터", () => {
    expect(sessionText("separate")).toBe("별도 세션");
    expect(sessionText("same")).toBe("같은 세션");
    expect(sessionText("zz")).toBe("zz");
    expect(sessionTip("same", "리더")).toBe("리더 세션 안에서 실행됩니다");
    expect(sessionTip("separate")).toBe("자기 세션을 따로 엽니다");
    expect(sessionChipView(null)).toBeUndefined();
    expect(sessionChipView("same", { iconOnly: true })).toMatchObject({ iconName: "corner-down-right", dashed: true, iconOnly: true });
    expect(sessionChipView("separate")).toMatchObject({ iconName: "git-fork" });
    expect(sessionChipView("zz")).toMatchObject({ iconName: "circle", title: "zz" });
  });
});
