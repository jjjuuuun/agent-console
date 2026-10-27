import { describe, expect, it } from "vitest";
import { ApiError, LOG_EMPTY_VALUE, logQuery } from "@agent-console/api-client";
import { ERROR_CODES, type ArchitectureView } from "@agent-console/contracts";
import { sampleCell, sampleEdge } from "@agent-console/arch-view/testing";
import { allNotCollected, classifyArchError, drillQuery, drillStepFor, dropAfter, mergeQuery, observedValue, resolveTarget, sourceKinds, targetQuery } from "./archLib";

// 칸·묶음·연결 이름은 모두 임의 값이다.
const view: ArchitectureView = {
  profile: "pf",
  event_total: 5,
  max_seq: 9,
  cells: [
    sampleCell("zz1", {
      label: "임의 칸",
      metrics: { count: { status: "observed", value: 4 } },
      selector: { arch: "pf:cell:zz1", arch_sources: ["s-a"] },
      drillable: true,
      groups: [
        { key: "k1", label: "묶음 일", metrics: { count: { status: "observed", value: 3 } }, selector: { arch: "pf:cell:zz1", arch_group: "k1" }, drill: { filter: "ff", value: "k1" } },
        { key: null, metrics: { count: { status: "observed", value: 1 } }, selector: { arch: "pf:cell:zz1", arch_group: "" }, drill: null },
      ],
    }),
    sampleCell("zz2", { status: "not_collected", metrics: { count: { status: "not_collected", value: null } } }),
  ],
  edges: [sampleEdge("ee1", "zz1", "zz2", { label: "임의 연결" }), sampleEdge("ee2", "zz2", "zz1", { kind: "structural", selector: null })],
  unassigned: { metrics: { count: { status: "observed", value: 1 } }, selector: { arch: "pf:unassigned" } },
  sources: [{ id: "s-a", kind: "kind-q", events: 3 }, { id: "s-b", events: 2 }],
};

describe("resolveTarget", () => {
  it("칸·연결·묶음·분류 안 됨의 선택자와 횟수를 뷰에서 찾는다", () => {
    expect(resolveTarget(view, { kind: "cell", id: "zz1" }, "(없음)")).toMatchObject({ name: "임의 칸", selector: { arch: "pf:cell:zz1" } });
    expect(resolveTarget(view, { kind: "edge", id: "ee1" }, "(없음)")?.name).toBe("임의 연결");
    expect(resolveTarget(view, { kind: "group", id: "zz1", group: "k1" }, "(없음)")).toMatchObject({ name: "묶음 일", cellName: "임의 칸" });
    expect(resolveTarget(view, { kind: "group", id: "zz1", group: null }, "(없음)")?.name).toBe("(없음)");
    expect(resolveTarget(view, { kind: "unassigned", id: "" }, "(없음)")?.selector.arch).toBe("pf:unassigned");
  });

  it("사라진 대상과 구조 연결(선택자 없음)은 undefined", () => {
    expect(resolveTarget(view, { kind: "cell", id: "없는 칸" }, "")).toBeUndefined();
    expect(resolveTarget(view, { kind: "edge", id: "ee2" }, "")).toBeUndefined();
    expect(resolveTarget({ ...view, unassigned: null }, { kind: "unassigned", id: "" }, "")).toBeUndefined();
  });
});

describe("targetQuery", () => {
  it("선택자 필드와 max_seq를 그대로 옮기고 이름 없는 묶음은 arch_group=로 보낸다", () => {
    const q = targetQuery({ arch: "pf:cell:zz1", arch_sources: ["s-a"] }, 9);
    expect(q).toEqual({ arch: "pf:cell:zz1", arch_sources: ["s-a"], max_seq: 9 });
    expect(logQuery(targetQuery({ arch: "pf:cell:zz1", arch_group: "" }, null))).toBe("?arch=pf%3Acell%3Azz1&arch_group=");
    expect(targetQuery({ arch: "a", arch_group: "" }, undefined)).toEqual({ arch: "a", arch_group: LOG_EMPTY_VALUE });
    expect(targetQuery({ arch: "a", arch_group: null, arch_sources: [] }, undefined)).toEqual({ arch: "a" });
  });
});

describe("하위 구조도", () => {
  it("묶음의 drill로 단계를 만들고 drill이 없는 묶음은 undefined", () => {
    expect(drillStepFor(view, "zz1", "k1", "(없음)")).toEqual({ filter: "ff", value: "k1", label: "묶음 일" });
    expect(drillStepFor(view, "zz1", null, "(없음)")).toBeUndefined();
    expect(drillStepFor(view, "zz2", "k1", "(없음)")).toBeUndefined();
  });

  it("묶음을 정하지 않으면 들어갈 수 있는 묶음이 하나일 때만 그 묶음으로 들어간다", () => {
    expect(drillStepFor(view, "zz1", undefined, "(없음)")?.value).toBe("k1");
    const two = { ...view, cells: [{ ...view.cells![0]!, groups: [...view.cells![0]!.groups!, { key: "k3", selector: { arch: "x" }, drill: { filter: "ff", value: "k3" } }] }] };
    expect(drillStepFor(two, "zz1", undefined, "(없음)")).toBeUndefined();
  });

  it("단계 필터를 이름별 값 목록으로 합치고 빵 부스러기로 돌아가면 뒤 단계가 사라진다", () => {
    const steps = [{ filter: "ff", value: "a", label: "A" }, { filter: "ff", value: "b", label: "B" }, { filter: "gg", value: "c", label: "C" }];
    expect(drillQuery(steps)).toEqual({ ff: ["a", "b"], gg: ["c"] });
    expect(dropAfter(steps, -1)).toEqual([]);
    expect(dropAfter(steps, 0)).toEqual([steps[0]]);
    expect(dropAfter(steps, 5)).toHaveLength(3);
  });

  it("mergeQuery는 같은 이름을 값 목록으로 잇고 빈 값은 건너뛴다", () => {
    expect(mergeQuery({ a: "1", t: [] }, { a: ["2"], t: ["x"] }, undefined, { b: "" })).toEqual({ a: ["1", "2"], t: ["x"], b: "" });
  });
});

describe("오류 분류와 상태", () => {
  it("서버 코드를 화면 상태 A·D·F·E로 가른다", () => {
    expect(classifyArchError(new ApiError(404, { code: ERROR_CODES.ARCHITECTURE_PROFILE_NOT_FOUND, message: "프로필 없음" })).kind).toBe("rules");
    expect(classifyArchError(new ApiError(422, { code: ERROR_CODES.ARCHITECTURE_SCOPE_TOO_LARGE, message: "큼", details: { events: 90, limit: 50 } }))).toMatchObject({ kind: "tooBig", events: 90, limit: 50 });
    expect(classifyArchError(new ApiError(422, { code: "architecture.invalid", message: "깨짐" })).kind).toBe("profile");
    expect(classifyArchError(new ApiError(500, { code: "x", message: "서버" })).kind).toBe("error");
    expect(classifyArchError(new Error("네트워크"))).toMatchObject({ kind: "error", message: "네트워크" });
  });

  it("지표는 관측된 값만 숫자로 보고 모든 칸이 수집 안 됨일 때만 C", () => {
    expect(observedValue({ status: "observed", value: 0 })).toBe(0);
    expect(observedValue({ status: "inferred", value: 3 })).toBeUndefined();
    expect(observedValue({ status: "not_collected", value: null })).toBeUndefined();
    expect(allNotCollected(view)).toBe(false);
    expect(allNotCollected({ ...view, cells: [view.cells![1]!] })).toBe(true);
    expect(allNotCollected({ ...view, cells: [] })).toBe(false);
  });

  it("출처 종류 이름은 종류가 없으면 출처 id로 대신하고 중복을 없앤다", () => {
    expect(sourceKinds(view)).toEqual(["kind-q", "s-b"]);
  });
});
