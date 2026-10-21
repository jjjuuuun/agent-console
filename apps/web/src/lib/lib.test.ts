import { describe, expect, it } from "vitest";
import type { Issue } from "@agent-console/contracts";
import { createSafeStorage, readJson } from "../app/storage";
import { formatClockTime, formatDuration, formatElapsed, formatRelative, slugify } from "./format";
import { countIssues, issueMessage, sortIssues, splitNodeIssues } from "./issues";

describe("issues", () => {
  const issues: Issue[] = [
    { severity: "error", code: "bad", message: "값 오류", node_id: "n1", path: "/greeting" },
    { severity: "warning", code: "w", message: "경고", node_id: "n1" },
    { severity: "info", code: "i", message: "정보", node_id: "n1", path: "/x" },
    { severity: "error", code: "other", message: "다른 노드", node_id: "n2", path: "/y" },
  ];
  it("config 경로가 있는 이슈만 폼 오류로 매핑한다", () => {
    const { fieldErrors, unmapped } = splitNodeIssues(issues, "n1");
    expect(fieldErrors).toEqual([{ path: "/greeting", message: "값 오류", severity: "error" }]);
    expect(unmapped.map((i) => i.code)).toEqual(["w", "i"]);
  });
  it("개수와 정렬", () => {
    expect(countIssues(issues)).toEqual({ error: 2, warning: 1, info: 1 });
    expect(sortIssues(issues).map((i) => i.code)).toEqual(["bad", "other", "w", "i"]);
  });
  it("검증기 키워드가 있는 영어 메시지는 한국어로, 한국어 서버 메시지는 그대로", () => {
    expect(issueMessage({ severity: "error", code: "x", message: "does not match pattern", details: { validator: "pattern" } })).toBe("형식이 올바르지 않습니다");
    expect(issueMessage({ severity: "error", code: "x", message: "이미 한국어", details: { validator: "pattern" } })).toBe("이미 한국어");
  });
});

describe("기타 순수 함수", () => {
  it("포맷", () => {
    expect(formatDuration(1200)).toBe("1.2초");
    expect(formatDuration(null)).toBe("–");
    expect(formatElapsed(12_000)).toBe("00:12");
    expect(formatRelative(100, 100_000 + 120_000)).toBe("2분 전");
    expect(slugify("My Graph 2")).toBe("my-graph-2");
  });
  it("저장소는 실패해도 던지지 않고, 키 나열·삭제를 지원한다", () => {
    const broken = { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("x"); }, removeItem: () => { throw new Error("x"); } } as unknown as Storage;
    const s = createSafeStorage(broken);
    expect(() => s.set("k", "v")).not.toThrow();
    expect(() => s.remove("k")).not.toThrow();
    expect(s.keys()).toEqual([]);
    expect(readJson(s, "k", 7)).toBe(7);
  });
});

describe("formatClockTime", () => {
  it("시각만 HH:MM:SS(24시간)로 보이고 값이 없으면 대시", () => {
    const sec = new Date(2026, 9, 19, 14, 1, 2).getTime() / 1000;
    expect(formatClockTime(sec)).toBe("14:01:02");
    expect(formatClockTime(new Date(2026, 9, 19, 0, 5, 9).getTime() / 1000)).toBe("00:05:09");
    expect(formatClockTime(null)).toBe("–");
    expect(formatClockTime(Number.NaN)).toBe("–");
  });
});
