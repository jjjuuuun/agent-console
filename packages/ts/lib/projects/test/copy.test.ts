import type { CopyApplyResult, CopyPlan, CopyPlanItem } from "@agent-console/contracts/projects";
import { describe, expect, test } from "vitest";

import {
  actionChoicesFor,
  buildApplyRequest,
  canSubmit,
  copyItemKey,
  createProjectsText,
  defaultActionFor,
  firstUsableRequested,
  initialSelections,
  itemsNeedingChoice,
  mergeReplan,
  selectAction,
  skipWarnings,
  suggestRename,
  summarizeResult,
  summarizeSelections,
  summaryMessage,
  targetStateLabel,
  validateNewId,
} from "@agent-console/projects";

// 종류 이름은 임의 문자열이다(코드에 고정된 종류가 없다는 R0 확인).
const item = (over: Partial<CopyPlanItem> & Pick<CopyPlanItem, "id" | "target_state">): CopyPlanItem => ({
  kind: "k1",
  name: over.id,
  reason: "requested",
  referenced_by: [],
  source_version: `s-${over.id}`,
  ...over,
});
const plan = (items: CopyPlanItem[]): CopyPlan => ({ items, warnings: [] });
const mixed = plan([
  item({ id: "team", target_state: "absent" }),
  item({ id: "pl", kind: "k2", target_state: "absent", reason: "referenced", referenced_by: [{ kind: "k1", id: "team", name: "리뷰 팀" }] }),
  item({ id: "guide", kind: "k3", target_state: "identical", reason: "referenced", referenced_by: [{ kind: "k2", id: "pl" }], target_version: "t-guide" }),
  item({ id: "rev", kind: "k2", target_state: "different", target_version: "t-rev" }),
]);

describe("기본 동작", () => {
  test.each([
    ["absent", undefined, "copy"],
    ["identical", undefined, "reuse"],
    ["different", undefined, null],
    ["brand_new", undefined, null],
    ["absent", "skip", "skip"],
    ["different", "overwrite", "overwrite"],
    ["absent", "overwrite", "copy"], // 선택지에 없는 서버 값은 무시
  ] as const)("%s + default_action=%s → %s", (state, given, want) => {
    expect(defaultActionFor({ target_state: state, default_action: given ?? null })).toBe(want);
  });

  test("선택지: 상태별 표, 모르는 상태는 내용이 다름과 같다", () => {
    expect(actionChoicesFor({ target_state: "absent" }).map((c) => c.action)).toEqual(["copy", "skip"]);
    expect(actionChoicesFor({ target_state: "identical" }).map((c) => c.action)).toEqual(["reuse", "rename", "skip"]);
    const different = actionChoicesFor({ target_state: "different" });
    expect(different.map((c) => c.action)).toEqual(["overwrite", "rename", "skip"]);
    expect(actionChoicesFor({ target_state: "?" })).toEqual(different);
    expect(different[2]?.label.key).toBe("copy.action.skip_keep");
    expect(targetStateLabel("?")).toEqual({ key: "copy.state.different" });
  });
});

describe("선택·검사", () => {
  test("내용이 다른 항목은 고를 때까지 제출 불가", () => {
    const sel = initialSelections(mixed);
    expect(itemsNeedingChoice(mixed, sel).map((i) => i.id)).toEqual(["rev"]);
    expect(canSubmit(mixed, sel)).toEqual({ allowed: false, reason: "need_choice" });
    const chosen = selectAction(sel, { kind: "k2", id: "rev" }, "overwrite");
    expect(canSubmit(mixed, chosen)).toEqual({ allowed: true, reason: null });
    expect(sel.get(copyItemKey({ kind: "k2", id: "rev" }))?.action).toBeNull(); // 원본 불변
  });

  test("전부 건너뛰면 제출 불가, 빈 계획도 불가", () => {
    let sel = initialSelections(mixed);
    for (const i of mixed.items!) sel = selectAction(sel, i, "skip");
    expect(canSubmit(mixed, sel).reason).toBe("all_skipped");
    expect(canSubmit(plan([]), new Map()).reason).toBe("empty");
  });

  test("새 이름: 제안은 -2부터 겹치지 않게, 검사는 비어 있음·문법·중복", () => {
    expect(suggestRename("pl", [])).toBe("pl-2");
    expect(suggestRename("pl", ["pl-2", "pl-3"])).toBe("pl-4");
    expect(validateNewId("", [])).toBe("empty");
    expect(validateNewId("한글", [])).toBe("invalid");
    expect(validateNewId("a b", [])).toBe("invalid");
    expect(validateNewId("pl-2", ["pl-2"])).toBe("taken");
    expect(validateNewId("pl-2", ["x"])).toBeNull();

    let sel = selectAction(initialSelections(mixed), { kind: "k2", id: "rev" }, "rename");
    expect(sel.get(copyItemKey({ kind: "k2", id: "rev" }))?.newId).toBe("rev-2");
    expect(canSubmit(mixed, sel).allowed).toBe(true);
    sel = new Map(sel).set(copyItemKey({ kind: "k2", id: "rev" }), { action: "rename", newId: "pl" });
    expect(canSubmit(mixed, sel, (i) => (i.kind === "k2" ? ["pl"] : [])).reason).toBe("bad_new_id");
  });

  test("가져오지 않기 경고: 연결 항목만, 문구는 키와 값", () => {
    let sel = initialSelections(mixed);
    sel = selectAction(sel, { kind: "k1", id: "team" }, "skip"); // 요청 항목 → 경고 없음
    expect(skipWarnings(mixed, sel)).toEqual([]);
    sel = selectAction(sel, { kind: "k2", id: "pl" }, "skip");
    sel = selectAction(sel, { kind: "k3", id: "guide" }, "skip");
    const warns = skipWarnings(mixed, sel);
    expect(warns.map((w) => w.item.id)).toEqual(["pl", "guide"]);
    const text = createProjectsText();
    expect(text(warns[0]!.message)).toBe("‘리뷰 팀’은(는) pl가 없어 실행 전에 막힙니다");
    expect(text(warns[1]!.message)).toContain("‘pl’");
    // 그대로 쓰기(reuse)는 건너뛰는 것이 아니다
    expect(skipWarnings(mixed, initialSelections(mixed))).toEqual([]);
  });

  test("요약: 개수와 (N)", () => {
    let sel = initialSelections(mixed);
    expect(summarizeSelections(mixed, sel)).toEqual({ copy: 2, reuse: 1, overwrite: 0, rename: 0, skip: 0, unset: 1, writes: 2 });
    sel = selectAction(sel, { kind: "k2", id: "rev" }, "rename");
    const s = summarizeSelections(mixed, sel);
    expect(s).toMatchObject({ rename: 1, unset: 0, writes: 3 });
    expect(createProjectsText()(summaryMessage(s))).toBe("복사 2 · 그대로 쓰기 1 · 덮어쓰기 0 · 새 이름 1 · 건너뜀 0");
  });
});

describe("적용 요청", () => {
  test("계획의 버전을 그대로 싣고, 새 이름은 rename일 때만", () => {
    let sel = initialSelections(mixed);
    sel = selectAction(sel, { kind: "k2", id: "rev" }, "rename");
    const req = buildApplyRequest(mixed, sel, { source: { project_id: null }, target: { project_id: "p1" } });
    expect(req).toEqual({
      source: { project_id: null },
      target: { project_id: "p1" },
      remove_source: false,
      items: [
        { kind: "k1", id: "team", action: "copy", source_version: "s-team" },
        { kind: "k2", id: "pl", action: "copy", source_version: "s-pl" },
        { kind: "k3", id: "guide", action: "reuse", source_version: "s-guide", target_version: "t-guide" },
        { kind: "k2", id: "rev", action: "rename", new_id: "rev-2", source_version: "s-rev", target_version: "t-rev" },
      ],
    });
    expect(buildApplyRequest(mixed, sel, { source: { project_id: null }, target: { project_id: "p1" }, removeSource: true }).remove_source).toBe(true);
  });

  test("고르지 않은 항목이 있으면 던진다", () => {
    expect(() => buildApplyRequest(mixed, initialSelections(mixed), { source: { project_id: null }, target: { project_id: "p1" } })).toThrow(/rev/);
  });
});

describe("결과", () => {
  const result: CopyApplyResult = {
    items: [
      { kind: "k1", id: "team", status: "renamed", new_id: "team-2" },
      { kind: "k2", id: "pl", status: "copied" },
      { kind: "k3", id: "guide", status: "reused" },
      { kind: "k2", id: "rev", status: "conflict" },
      { kind: "k9", id: "z", status: "skipped" },
      { kind: "k9", id: "w", status: "copied", issue: { severity: "error", code: "secret", message: "비밀 값은 저장할 수 없습니다" } },
      { kind: "k9", id: "v", status: "teleported" },
    ],
  };

  test("행 종류와 문구", () => {
    const s = summarizeResult(result);
    expect(s).toMatchObject({ total: 7, ok: 3, skipped: 1, conflicts: 1, errors: 2, allOk: false });
    expect(s.rows.map((r) => r.rowKind)).toEqual(["ok", "ok", "ok", "conflict", "skipped", "error", "error"]);
    const text = createProjectsText();
    expect(text(s.rows[0]!.label!)).toBe("새 이름으로 추가함 → team-2");
    expect(text(s.rows[3]!.label!)).toBe("계획 뒤에 바뀌어 적용하지 않았습니다");
    expect(s.rows[5]!.issueMessage).toBe("비밀 값은 저장할 수 없습니다");
    expect(s.rows[6]!.label).toBeNull();
    expect(s.conflictKeys).toEqual([{ kind: "k2", id: "rev" }]);
  });

  test("전부 성공이면 allOk", () => {
    expect(summarizeResult({ items: [{ kind: "k", id: "a", status: "copied" }, { kind: "k", id: "b", status: "skipped" }] }).allOk).toBe(true);
  });

  test("새 대화 대화상자가 고를 첫 항목은 요청 항목 중 사용 가능해진 것(새 이름이면 새 id)", () => {
    expect(firstUsableRequested(mixed, result)).toEqual({ kind: "k1", id: "team-2" });
    expect(firstUsableRequested(mixed, { items: [{ kind: "k1", id: "team", status: "conflict" }] })).toBeNull();
  });

  test("conflict 행만 다시 계획해 합친다", () => {
    const fresh = plan([item({ id: "rev", kind: "k2", target_state: "identical", source_version: "s2", target_version: "t2" })]);
    const merged = mergeReplan(mixed, fresh);
    expect(merged.items!.map((i) => [i.id, i.target_state])).toEqual([["team", "absent"], ["pl", "absent"], ["guide", "identical"], ["rev", "identical"]]);
  });
});
