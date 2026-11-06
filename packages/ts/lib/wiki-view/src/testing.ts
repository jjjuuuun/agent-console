/**
 * 테스트·예제용 표본 데이터. 계약 모양(`@agent-console/contracts/wiki`)을 따른다.
 * 열린 문자열(동작·종류·심각도·코드)에는 일부러 기본 어휘와 무관한 낱말을 섞었다(코드가 이름을 모른다는 시험용).
 */
import type {
  WikiGraph, WikiIssue, WikiLink, WikiPageSummary, WikiPageVersion, WikiPageView, WikiSearchHit,
} from "@agent-console/contracts/wiki";
import type { WikiDisplay } from "./display";

export const SAMPLE_NOW = 1_795_000_000;

/** 한글·서로게이트 쌍(이모지)·ASCII가 섞인 본문. 링크 범위(UTF-16)는 `sampleLinks`가 정확히 가리킨다. */
export const SAMPLE_CONTENT = "# 시작 😀\n\n첫째 [[둘째 페이지]] 그리고 🙂🙂 ((없는곳)) 그리고 {{x:열기}} 끝 ↗ <밖>.\n";

function at(content: string, needle: string): [number, number] {
  const s = content.indexOf(needle);
  if (s < 0) throw new Error(`표본에 없는 조각: ${needle}`);
  return [s, s + needle.length];
}

/** `SAMPLE_CONTENT`의 링크 4개: ok · broken · scheme · outside. 상태 이름은 계약 문서 상수다. */
export function sampleLinks(content: string = SAMPLE_CONTENT): WikiLink[] {
  const [a0, a1] = at(content, "[[둘째 페이지]]");
  const [b0, b1] = at(content, "((없는곳))");
  const [c0, c1] = at(content, "{{x:열기}}");
  const [d0, d1] = at(content, "<밖>");
  return [
    { start: a0, end: a1, raw: "[[둘째 페이지]]", kind: "k1", rule_id: "r1", target: "둘째 페이지", label: "둘째", anchor: null, resolved: "notes/second", status: "ok" },
    { start: b0, end: b1, raw: "((없는곳))", kind: "k2", rule_id: "r2", target: "없는곳", label: "없는곳", resolved: null, broken: true, suggested_path: "notes/none", status: "broken" },
    { start: c0, end: c1, raw: "{{x:열기}}", kind: "k3", rule_id: "r3", target: "열기", label: "열기", status: "scheme", scheme_target: { role: "elsewhere", id_from: "/target" } },
    { start: d0, end: d1, raw: "<밖>", kind: "k4", rule_id: "r4", target: "밖", label: "밖", outside: true, status: "outside" },
  ];
}

export function samplePageView(overrides: Partial<WikiPageView> = {}): WikiPageView {
  const content = overrides.content ?? SAMPLE_CONTENT;
  return {
    page: { path: "notes/first", title: "첫 페이지", tags: [], aliases: [], bytes: content.length, updated_at: SAMPLE_NOW, links_out: 4, backlinks: 0, broken_links: 1, orphan: false, home: false, issues: [] },
    content,
    content_hash: "h1",
    front_matter: {},
    headings: [{ level: 1, text: "시작 😀", line: 1 }],
    links: overrides.content === undefined ? sampleLinks(content) : [],
    backlinks: [],
    issues: [],
    ...overrides,
  };
}

export function samplePages(): WikiPageSummary[] {
  const p = (path: string, extra: Partial<WikiPageSummary> = {}): WikiPageSummary => ({ path, title: extra.title ?? path.split("/").pop()!, ...extra });
  return [
    p("notes/second", { title: "둘째" }),
    p("notes/first", { title: "첫째", broken_links: 2 }),
    p("notes/page10", { title: "페이지 10" }),
    p("notes/page2", { title: "페이지 2" }),
    p("index", { title: "처음", home: true }),
    p("lonely", { title: "혼자", orphan: true }),
    p("deep/er/x", { title: "깊은" }),
  ];
}

export function manyPages(n: number): WikiPageSummary[] {
  return Array.from({ length: n }, (_, i) => ({ path: `dir${i % 20}/p${i}`, title: `페이지 ${i}` }));
}

/** 동작 `zap`·`weird`·쓴 주체 `robot`은 표시 표에 없는 값(원문 + 중립). */
export function sampleVersions(): WikiPageVersion[] {
  return [
    { version: 5, op: "update", sha256: "a", bytes: 10, at: SAMPLE_NOW - 30, author: { kind: "agent", agent_id: "ag-7", label: "정리 담당", run_id: "run-1234567890", root_run_id: "root-1", node_path: ["n1", "n2"] }, message: "한 줄 고침" },
    { version: 4, op: "zap", sha256: "b", bytes: 9, at: SAMPLE_NOW - 7200, author: { kind: "robot", agent_id: null, label: null } },
    { version: 3, op: "external", sha256: "c", bytes: 9, at: SAMPLE_NOW - 86_400 * 3, author: { kind: "external" } },
    { version: 1, op: "create", sha256: "d", bytes: 5, at: SAMPLE_NOW - 86_400 * 9, author: { kind: "user" } },
  ];
}

/** 표시 표 표본 — 일부 값만 정의한다. */
export function sampleDisplay(): WikiDisplay {
  return {
    ops: { create: { label: "만듦", tone: "success" }, update: { label: "고침" }, external: { label: "외부 변경", tone: "warning" } },
    authorKinds: { user: { label: "사람", icon: "user" }, agent: { label: "에이전트", icon: "agent" }, external: { label: "외부", icon: "external" } },
    linkStatuses: { ok: { label: "해석됨" }, broken: { label: "끊긴 링크", icon: "link-broken", tone: "danger" }, outside: { label: "폴더 밖" }, scheme: { label: "다른 기능", icon: "external-link" } },
    severities: { error: { label: "오류", tone: "danger" }, warning: { label: "경고", tone: "warning" }, info: { label: "정보", tone: "info" } },
    codes: { broken_link: { label: "끊긴 링크" } },
    sources: { default: { label: "기본" }, settings: { label: "설정" } },
  };
}

/** 노드 5(중심·끊긴·고아·스킴·보통), 엣지 5(양방향 한 쌍·×3 포함). */
export function sampleGraph(): WikiGraph {
  return {
    nodes: [
      { path: "a", title: "가", home: true, depth: 0 },
      { path: "b", title: "나", depth: 1 },
      { path: "c", title: "다", broken: true, depth: 1 },
      { path: "d", title: "라", orphan: true, depth: 2 },
      { path: "e", title: "마", scheme: "x", depth: 2 },
    ],
    edges: [
      { from: "a", to: "b", count: 3 },
      { from: "b", to: "a" },
      { from: "a", to: "c" },
      { from: "b", to: "e" },
      { from: "b", to: "d" },
    ],
    truncated: false,
    total: null,
  };
}

/** 심각도 `purple`·코드 `custom_x`는 표시 표에 없는 값. */
export function sampleIssues(n = 4): WikiIssue[] {
  const base: WikiIssue[] = [
    { severity: "warning", code: "broken_link", message: "끊긴 링크 ‘없는곳’", path: "notes/first", details: { line: 3 } },
    { severity: "error", code: "wiki.rule_violation", message: "금지 패턴이 들어 있습니다", path: "notes/second", details: { line: 12, rule_id: "no-secrets" } },
    { severity: "purple" as WikiIssue["severity"], code: "custom_x", message: "알 수 없는 종류의 점검", path: "index" },
    { severity: "info", code: "orphan", message: "아무 데서도 가리키지 않습니다", path: "lonely" },
  ];
  return Array.from({ length: n }, (_, i) => ({ ...base[i % base.length]!, path: `${base[i % base.length]!.path}${i >= base.length ? `-${i}` : ""}` }));
}

/** 조각 안 이모지·한글 범위(UTF-16). */
export function sampleHits(): WikiSearchHit[] {
  const snippet = "앞 😀 한글검색어 뒤 🙂";
  const s = snippet.indexOf("한글검색어");
  return [
    { path: "notes/second", title: "둘째", snippet, marks: [{ start: s, end: s + 5 }] },
    { path: "index", title: "", snippet: "plain text" },
  ];
}
