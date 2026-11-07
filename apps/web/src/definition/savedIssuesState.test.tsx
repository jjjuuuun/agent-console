import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { readSavedIssues, savedIssuesState, useCarriedSaveIssues } from "./savedIssuesState";

const w = { severity: "warning" as const, code: "secret.plain_found", message: "평문 비밀" };

describe("저장 경고를 다음 화면으로 넘기기", () => {
  it("경고가 없으면 state를 만들지 않고, 있으면 읽어 낸다", () => {
    expect(savedIssuesState(undefined)).toBeUndefined();
    expect(savedIssuesState([])).toBeUndefined();
    expect(readSavedIssues(savedIssuesState([w]))).toEqual([w]);
    expect(readSavedIssues(null)).toEqual([]);
    expect(readSavedIssues({ savedIssues: "x" })).toEqual([]);
  });
  it("이 화면에서 저장하기 전에는 넘어온 경고를, 저장 뒤에는 이 화면 경고(빈 목록 포함)를 보인다", () => {
    const first: never[] = [];
    const { result, rerender } = renderHook(({ own }) => useCarriedSaveIssues(own, [w]), { initialProps: { own: first as readonly (typeof w)[] } });
    expect(result.current).toEqual([w]);
    act(() => rerender({ own: [] }));
    expect(result.current).toEqual([]);
  });
});
