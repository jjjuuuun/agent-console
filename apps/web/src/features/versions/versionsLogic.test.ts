import { describe, expect, it } from "vitest";
import {
  compareTarget,
  contentStatus,
  countOps,
  diffTotals,
  isSameDiff,
  languageOfPath,
  matchesQuery,
  previewValue,
  readIssues,
  readablePath,
  resolveLabelKeys,
  DEFAULT_DIFF_LABEL_KEYS,
  schemaTitleResolver,
  textDiffBlocked,
} from "./versionsLogic";

const doc = {
  title: "임의 문서",
  items: [{ label: "첫째", cfg: { mode: "a" } }, { name: "둘째" }, { x: 1 }],
};

describe("resolveLabelKeys", () => {
  it("생략·빈 목록·공백뿐인 목록은 기본값으로, 값이 있으면 그 순서 그대로 쓴다", () => {
    expect(resolveLabelKeys(undefined)).toBe(DEFAULT_DIFF_LABEL_KEYS);
    expect(resolveLabelKeys(null)).toBe(DEFAULT_DIFF_LABEL_KEYS);
    expect(resolveLabelKeys([" "])).toBe(DEFAULT_DIFF_LABEL_KEYS);
    expect(resolveLabelKeys(["cfg", " ", "id"])).toEqual(["cfg", "id"]);
    expect(readablePath("/items/0", doc, { labelKeys: resolveLabelKeys(["cfg"]) })).toBe("items #0");
  });
});

describe("readablePath", () => {
  it("배열 인덱스는 원소 이름 후보 키(label -> name)로, 없으면 #인덱스로 바꾼다", () => {
    expect(readablePath("/items/0/cfg/mode", doc)).toBe("items “첫째” › cfg › mode");
    expect(readablePath("/items/1", doc)).toBe("items “둘째”");
    expect(readablePath("/items/2/x", doc)).toBe("items #2 › x");
  });
  it("후보 키 목록은 호출자가 바꿀 수 있다", () => {
    expect(readablePath("/items/1", doc, { labelKeys: ["zzz"] })).toBe("items #1");
  });
  it("문서에 없는 위치·문서가 없을 때도 원문 세그먼트로 읽힌다", () => {
    expect(readablePath("/items/9/label", doc)).toBe("items #9 › label");
    expect(readablePath("/a/b", undefined)).toBe("a › b");
    expect(readablePath("", doc)).toBe("/");
  });
  it("스키마 title이 있으면 객체 키를 바꾼다(~1 같은 이스케이프 포함)", () => {
    const resolver = schemaTitleResolver({
      type: "object",
      properties: { items: { type: "array", title: "목록", items: { $ref: "#/$defs/It" } } },
      $defs: { It: { type: "object", properties: { cfg: { title: "설정", type: "object" } } } },
    });
    expect(readablePath("/items/0/cfg", doc, { schemaTitles: resolver })).toBe("목록 “첫째” › 설정");
    expect(readablePath("/a~1b", { "a/b": 1 })).toBe("a/b");
  });
});

describe("previewValue", () => {
  it("스칼라는 80자에서 말줄임, 객체·배열은 요약과 복합 표시", () => {
    const long = previewValue("가".repeat(100));
    expect(long.text).toBe(`${"가".repeat(80)}…`);
    expect(long.truncated).toBe(true);
    expect(previewValue({ a: 1, b: 2 })).toMatchObject({ text: "{… 2}", complex: true });
    expect(previewValue([1, 2, 3]).text).toBe("[… 3]");
    expect(previewValue("***").text).toBe("***");
    expect(previewValue(undefined).text).toBe("");
  });
});

describe("matchesQuery / countOps", () => {
  const changes = [
    { op: "add" as const, path: "/a", after: "needle" },
    { op: "replace" as const, path: "/s", before: "***", after: "***", secret: true },
    { op: "remove" as const, path: "/r", before: 1 },
  ];
  it("경로·읽는 경로·값으로 찾고 비밀 값은 값으로 찾지 않는다", () => {
    expect(matchesQuery(changes[0]!, "A", "needle")).toBe(true);
    expect(matchesQuery(changes[0]!, "항목", "항목")).toBe(true);
    expect(matchesQuery(changes[1]!, "/s", "***")).toBe(false);
    expect(matchesQuery(changes[1]!, "/s", "/S")).toBe(true);
    expect(matchesQuery(changes[2]!, "r", "")).toBe(true);
  });
  it("동작별 개수", () => {
    expect(countOps(changes)).toEqual({ add: 1, remove: 1, replace: 1 });
  });
});

describe("compareTarget", () => {
  const versions = ["cur", "v2", "v3", "v4"].map((version_hash) => ({ version_hash }));
  it("현재와 모드: 체크한 버전, 없으면 직전 버전, 현재 자신은 건너뜀", () => {
    expect(compareTarget(versions, ["v3"], "current")).toEqual({ from: "v3", to: undefined });
    expect(compareTarget(versions, [], "current")).toEqual({ from: "v2", to: undefined });
    expect(compareTarget(versions, ["cur"], "current")).toEqual({ from: "v2", to: undefined });
    expect(compareTarget([{ version_hash: "only" }], [], "current")).toBeUndefined();
  });
  it("두 버전 모드: 오래된 것이 앞, 새 쪽이 현재면 대상 생략", () => {
    expect(compareTarget(versions, ["v2", "v4"], "pair")).toEqual({ from: "v4", to: "v2" });
    expect(compareTarget(versions, ["cur", "v3"], "pair")).toEqual({ from: "v3", to: undefined });
    expect(compareTarget(versions, ["v2"], "pair")).toBeUndefined();
  });
});

describe("기타", () => {
  it("본문 변경 상태는 해시 유무로 정한다", () => {
    expect(contentStatus({ path: "a", after_hash: "x" })).toBe("added");
    expect(contentStatus({ path: "a", before_hash: "x" })).toBe("removed");
    expect(contentStatus({ path: "a", before_hash: "x", after_hash: "y" })).toBe("changed");
  });
  it("확장자로 언어를 고르고 모르면 text", () => {
    expect(languageOfPath("skills/a/SKILL.md")).toBe("markdown");
    expect(languageOfPath("x.JSON")).toBe("json");
    expect(languageOfPath("run.sh")).toBe("text");
    expect(languageOfPath("toString")).toBe("text");
  });
  it("512KB 초과면 텍스트 비교 불가", () => {
    expect(textDiffBlocked([10, 600 * 1024])).toBe("too_large");
    expect(textDiffBlocked([10, undefined])).toBeUndefined();
  });
  it("변경 합계·같음 판정·이슈 읽기", () => {
    expect(diffTotals({ changes: [{ op: "add", path: "/a" }], content_changes: [] })).toEqual({ fields: 1, content: 0 });
    expect(isSameDiff({ changes: [], content_changes: [] })).toBe(true);
    expect(readIssues([{ path: "/a", message: "m", code: "c" }, { message: "n" }, 5])).toEqual([
      { path: "/a", message: "m", code: "c" },
      { path: "", message: "n" },
    ]);
    expect(readIssues(undefined)).toEqual([]);
  });
});
