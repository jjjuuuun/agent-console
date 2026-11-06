import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { getContractSchema } from "@agent-console/contracts";
import type { SpecSummary } from "@agent-console/contracts/sdd";
import type { SchemaNode } from "../../lib/schemaTools";
import { gapDisplay, SDD_TAB_DEFS, verificationDisplay } from "./sddConfig";
import { mergeSection, ruleSections, sectionValue, issueInSection } from "./ruleSections";
import { filterSpecs } from "./SpecListScreen";
import { classifySddError } from "./sddErrors";
import { ApiError } from "@agent-console/api-client";
import { setList } from "./params";

describe("noHardcoding: 스펙 화면 소스", () => {
  const files = readdirSync(__dirname).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\.tsx?$/.test(f) && f !== "messages.ts");
  const strip = (t: string) => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  const literals = (t: string) => [...strip(t).matchAll(/(["'`])((?:\\.|(?!\1)[^\\\n])*)\1/g)].map((m) => m[2] as string);

  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(8));

  it("모듈 id(mod-·link-)와 서버 라벨 접두 `sdd.`가 따옴표 문자열에 없다", () => {
    const hits: string[] = [];
    for (const f of files) for (const lit of literals(readFileSync(join(__dirname, f), "utf8"))) if (/^(mod|link|ac-mod|ac-link)-[a-z]/.test(lit) || /^sdd\./.test(lit)) hits.push(`${f}: ${lit}`);
    expect(hits).toEqual([]);
  });

  it("작업·문서 상태 이름(예: todo·done·doing·review·draft·approved)이 코드에 없다", () => {
    const names = /^(todo|done|doing|in_progress|review|draft|approved)$/i;
    const hits: string[] = [];
    for (const f of files) for (const lit of literals(readFileSync(join(__dirname, f), "utf8"))) if (names.test(lit)) hits.push(`${f}: ${lit}`);
    expect(hits).toEqual([]);
  });

  it("서버 데이터 파일(sddData.json)은 상태 이름 대신 계약 어휘 표만 가진다", () => {
    const text = readFileSync(resolve(__dirname, "sddData.json"), "utf8");
    expect(text).not.toMatch(/"(todo|done|doing|draft|approved)"/);
  });
});

describe("표시 데이터", () => {
  it("빈 곳·검증 값은 표에서 톤을 읽고, 모르는 값은 기본 톤 + 문구 키 없음", () => {
    expect(gapDisplay("verification_failed").tone).toBe("danger");
    expect(gapDisplay("no_such_code")).toEqual({ tone: "warning" });
    expect(verificationDisplay("pass").tone).toBe("success");
    expect(verificationDisplay("제멋대로")).toEqual({ tone: "neutral" });
  });
  it("탭 목록은 데이터이고 id가 중복되지 않는다", () => {
    const ids = SDD_TAB_DEFS.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.length).toBeGreaterThanOrEqual(3);
  });
});

describe("규칙 섹션(스키마에서)", () => {
  const schema = getContractSchema("SpecDefinition") as SchemaNode;
  const sections = ruleSections(schema);
  it("고급 속성(종류·id 등)은 빠지고, 객체 속성(규칙)은 하위 속성마다 섹션이 된다", () => {
    expect(sections.length).toBeGreaterThan(5);
    expect(sections.some((s) => s.path.length === 2)).toBe(true);
    expect(sections.every((s) => s.title !== "")).toBe(true);
    expect(new Set(sections.map((s) => s.id)).size).toBe(sections.length);
  });
  it("값 꺼내기·합치기는 순수하고 비면 키를 지운다", () => {
    const nested = sections.find((s) => s.path.length === 2);
    const flat = sections.find((s) => s.path.length === 1);
    expect(nested && flat).toBeTruthy();
    const [c, k] = (nested as { path: readonly string[] }).path as [string, string];
    const base = { [c]: { [k]: ["x"], other: 1 } };
    expect(sectionValue(base, nested!)).toEqual({ [k]: ["x"] });
    const merged = mergeSection(base, nested!, { [k]: ["y"] });
    expect(merged[c]).toEqual({ [k]: ["y"], other: 1 });
    expect(base[c]).toEqual({ [k]: ["x"], other: 1 });
    expect(mergeSection(base, nested!, {})[c]).toEqual({ other: 1 });
    const f = (flat as { path: readonly string[] }).path[0] as string;
    expect(mergeSection({ [f]: "a" }, flat!, { [f]: "b" })).toEqual({ [f]: "b" });
    expect(mergeSection({ [f]: "a" }, flat!, {})).toEqual({});
  });
  it("검사 이슈 경로가 섹션에 속하는지 가른다", () => {
    const nested = sections.find((s) => s.path.length === 2)!;
    expect(issueInSection(`${nested.pointer}/0/x`, nested)).toBe(true);
    expect(issueInSection(`${nested.pointer}zz`, nested)).toBe(false);
    expect(issueInSection(null, nested)).toBe(false);
  });
});

describe("목록 거르기·오류 분류·주소 인자", () => {
  const specs: SpecSummary[] = [
    { id: "a", name: "가", updated_at: 1, ready: 0, documents: [{ id: "d", state: "s1" }] },
    { id: "b", name: "나", updated_at: 3, ready: 2, documents: [{ id: "d", state: "s2" }] },
  ];
  it("갱신 시각 내림차순, 이름·문서 상태·준비 거르기", () => {
    expect(filterSpecs(specs, "", new Set(), false).map((s) => s.id)).toEqual(["b", "a"]);
    expect(filterSpecs(specs, "가", new Set(), false).map((s) => s.id)).toEqual(["a"]);
    expect(filterSpecs(specs, "", new Set(["s2"]), false).map((s) => s.id)).toEqual(["b"]);
    expect(filterSpecs(specs, "", new Set(), true).map((s) => s.id)).toEqual(["b"]);
  });
  it("오류 코드를 화면 종류로 나눈다", () => {
    const e = (code: string, details = {}) => new ApiError(409, { code, message: "m", details });
    expect(classifySddError(e("sdd.spaces_unavailable"), "f").kind).toBe("unavailable");
    expect(classifySddError(e("sdd.not_found"), "f").kind).toBe("notFound");
    expect(classifySddError(e("project.folder_missing"), "f").kind).toBe("problem");
    expect(classifySddError(e("folders.invalid_path", { reason: "reserved" }), "f")).toMatchObject({ kind: "problem" });
    expect(classifySddError(e("x.y"), "f")).toMatchObject({ kind: "generic", code: "x.y" });
    expect(classifySddError(new Error("net"), "f")).toEqual({ kind: "generic", message: "net" });
  });
  it("setList는 같은 이름의 값을 통째로 바꾼다", () => {
    const p = new URLSearchParams("a=1&s=x&s=y");
    setList(p, "s", ["z"]);
    expect(p.getAll("s")).toEqual(["z"]);
    setList(p, "s", []);
    expect(p.has("s")).toBe(false);
    expect(p.get("a")).toBe("1");
  });
});
