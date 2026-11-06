import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { KNOWN_WIKI_AUTHOR_KINDS, KNOWN_WIKI_IMPORT_STATUSES, KNOWN_WIKI_LINK_STATUSES, KNOWN_WIKI_LINT_CODES, KNOWN_WIKI_VERSION_OPS } from "@agent-console/contracts/constants";
import { authorLabel, resolveDisplay } from "@agent-console/wiki-view";
import data from "./wikiData.json";
import display from "./wikiDisplay.json";
import { buildWikiDisplay, importStatusDisplay, severityTone } from "./wikiConfig";
import { classifyWikiError } from "./wikiErrors";
import { routeWordOf } from "./PageDialogs";
import { filterWikis } from "./WikiListScreen";
import { lintBadge } from "./WikiScreen";
import { buildWikiShortcuts, WIKI_SHORTCUT_DEFS } from "./wikiShortcuts";

const err = (status: number, code: string, details: Record<string, unknown> = {}, message = "서버 문장") => new ApiError(status, { code, message, details });

describe("오류 분류", () => {
  it("규칙 거부는 서버가 준 규칙 id·메시지·줄을 그대로 담는다", () => {
    expect(classifyWikiError(err(422, "wiki.rule_rejected", { rule_id: "r-임의", message: "금지", lines: [3, 4] }), "x")).toEqual({ kind: "ruleRejected", ruleId: "r-임의", message: "금지", lines: [3, 4] });
  });
  it("비밀 거부는 줄 번호만(값 없음), 크기 초과는 한도, 404는 기록 유무", () => {
    expect(classifyWikiError(err(422, "wiki.secret_rejected", { issues: [{ details: { lines: [2] } }] }), "x")).toMatchObject({ kind: "secretRejected", lines: [2] });
    expect(classifyWikiError(err(422, "wiki.too_large", { limit: 1024 }), "x")).toMatchObject({ kind: "tooLarge", limit: 1024 });
    expect(classifyWikiError(err(404, "wiki.page_not_found", { path: "a", has_history: true }), "x")).toEqual({ kind: "pageNotFound", hasHistory: true });
    expect(classifyWikiError(err(404, "wiki.page_not_found", { path: "a" }), "x")).toEqual({ kind: "pageNotFound", hasHistory: false });
  });
  it("연동 꺼짐·충돌·기록 없음·프로젝트 문제·모르는 코드", () => {
    expect(classifyWikiError(err(409, "wiki.spaces_unavailable"), "x").kind).toBe("unavailable");
    expect(classifyWikiError(err(412, "version_conflict"), "x").kind).toBe("conflict");
    expect(classifyWikiError(err(409, "wiki.history_unavailable"), "x").kind).toBe("historyUnavailable");
    expect(classifyWikiError(err(409, "project.config_readonly"), "x").kind).toBe("problem");
    expect(classifyWikiError(err(500, "뭔가"), "x")).toMatchObject({ kind: "generic", code: "뭔가" });
    expect(classifyWikiError(new Error("끊김"), "x")).toEqual({ kind: "generic", message: "끊김" });
  });
});

describe("표시 표(wikiDisplay.json)", () => {
  const values = (o: Record<string, string>) => Object.values(o);
  it("키는 계약이 이름 붙인 문서 상수뿐이다", () => {
    expect(Object.keys(display.ops).sort()).toEqual(values(KNOWN_WIKI_VERSION_OPS).sort());
    expect(Object.keys(display.authorKinds).sort()).toEqual(values(KNOWN_WIKI_AUTHOR_KINDS).sort());
    expect(Object.keys(display.linkStatuses).sort()).toEqual(values(KNOWN_WIKI_LINK_STATUSES).sort());
    expect(Object.keys(display.codes).sort()).toEqual(values(KNOWN_WIKI_LINT_CODES).sort());
    expect(Object.keys(display.importStatuses).sort()).toEqual(values(KNOWN_WIKI_IMPORT_STATUSES).sort());
  });
  it("모르는 동작·종류·상태는 원문 + 중립으로 떨어진다", () => {
    const d = buildWikiDisplay();
    expect(resolveDisplay(d.ops, "update")).toMatchObject({ label: "수정", known: true });
    expect(resolveDisplay(d.ops, "zap")).toMatchObject({ label: "zap", tone: "neutral", known: false });
    expect(authorLabel({ kind: "robot" }, d)).toBe("robot");
    expect(authorLabel({ kind: "agent", agent_id: "ag", label: "이름" }, d)).toBe("이름");
    expect(importStatusDisplay("뭔가")).toEqual({ tone: "neutral", label: "뭔가" });
    expect(severityTone("purple")).toBe("neutral");
  });
});

describe("순수 함수", () => {
  it("위키 목록 거르기·정렬: 이름·설명·id 부분 일치, 한국어 이름 순", () => {
    const list = [{ id: "b", name: "나", description: "두번째" }, { id: "a", name: "가" }, { id: "c", name: "다 노트" }];
    expect(filterWikis(list, "").map((w) => w.id)).toEqual(["a", "b", "c"]);
    expect(filterWikis(list, "노트").map((w) => w.id)).toEqual(["c"]);
    expect(filterWikis(list, "두번").map((w) => w.id)).toEqual(["b"]);
  });
  it("주소와 겹쳐 읽을 수 없는 이름은 새 경로 입력에서 알린다", () => {
    expect(routeWordOf("a/history")).toBe("history");
    expect(routeWordOf("history/a")).toBeUndefined();
  });
  it("점검 배지는 위험·경고 톤인 심각도만 센다(모르는 심각도는 세지 않는다)", () => {
    expect(lintBadge({ error: 2, warning: 3, info: 9, purple: 4 })).toBe(5);
    expect(lintBadge(undefined)).toBe(0);
  });
  it("단축키 표는 핸들러가 있는 동작만 등록하고 단일 문자 키는 수식키를 요구하지 않는다", () => {
    const defs = buildWikiShortcuts({ newPage: () => undefined, panel: () => undefined });
    expect(defs.map((d) => d.id).sort()).toEqual(["wiki.new", "wiki.panel"]);
    expect(defs.find((d) => d.id === "wiki.new")?.modifierRequired).toBeUndefined();
    expect(defs.find((d) => d.id === "wiki.panel")?.modifierRequired).toBe(true);
    expect(new Set(WIKI_SHORTCUT_DEFS.map((d) => d.keys)).size).toBe(WIKI_SHORTCUT_DEFS.length);
  });
  it("주소 인자 이름과 탭 목록은 데이터에서 온다", () => {
    expect(data.tabs.map((t) => t.id)).toContain(data.defaultTab);
  });
});

describe("noHardcoding: 위키 화면 코드", () => {
  const dir = resolve(__dirname);
  const files = readdirSync(dir).filter((f) => /\.(tsx?|json)$/.test(f) && !/\.test\.tsx?$/.test(f) && f !== "wikiTestSetup.tsx");
  const strip = (t: string) => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  const literals = (t: string) => [...strip(t).matchAll(/(["'`])((?:\\.|(?!\1)[^\\\n])*)\1/g)].map((m) => m[2] as string);
  it("검사 대상이 있다", () => expect(files.length).toBeGreaterThan(15));
  it("링크 패턴·머리말 키·모듈 id·규칙 동작 이름이 따옴표 문자열로 나오지 않는다", () => {
    const forbidden = [/\[\[|\]\]|\(\(|\{\{|\}\}/, /^(wikilink|markdown_link|front_?matter|tags|aliases|title_sources)$/, /^(mod|link|ac-mod|ac-link)-[a-z]/, /^(reject|warn)$/];
    const hits: string[] = [];
    for (const f of files) {
      for (const lit of literals(readFileSync(join(dir, f), "utf8"))) {
        if (forbidden.some((re) => re.test(lit))) hits.push(`${f}: ${lit}`);
      }
    }
    expect(hits).toEqual([]);
  });
  it("위키 이름·페이지 경로 예시가 문구 표에 없다", () => {
    const text = readFileSync(join(dir, "messages.ts"), "utf8");
    expect(text).not.toMatch(/decisions\/|notes\/|payments/);
  });
});
