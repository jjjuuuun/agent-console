import { describe, expect, it, vi } from "vitest";
import type { WikiLink } from "@agent-console/contracts/wiki";
import { authorLabel, resolveDisplay, severityRank } from "./display";
import { formatRelative } from "./format";
import { createElkGraphLayout, edgeGeometry, graphToFlow, gridPositions, nearestNode } from "./graph";
import { escapeLinkText, linkifySource, linkLabel, linkMarks, parseLinkHref, usableLinks } from "./linkify";
import { splitByMarks } from "./marks";
import { defaultMessages } from "./messages";
import { SAMPLE_CONTENT, sampleGraph, sampleLinks, samplePages, SAMPLE_NOW } from "./testing";
import { allFolders, ancestorFolders, buildTree } from "./tree";

const link = (start: number, end: number, extra: Partial<WikiLink> = {}): WikiLink => ({ start, end, raw: "", kind: "k", rule_id: "r", status: "ok", ...extra });

describe("linkifySource — UTF-16 범위 (수용 기준 6)", () => {
  it("표본의 링크 범위가 정확히 그 글자를 가리킨다", () => {
    const links = sampleLinks();
    expect(links.map((l) => SAMPLE_CONTENT.slice(l.start, l.end))).toEqual(["[[둘째 페이지]]", "((없는곳))", "{{x:열기}}", "<밖>"]);
    // 앞에 이모지(서로게이트 쌍)가 있어 코드 포인트 인덱스와 UTF-16 인덱스가 어긋나는 표본임을 확인
    expect(Array.from(SAMPLE_CONTENT).length).toBeLessThan(SAMPLE_CONTENT.length);
  });
  it("한글·이모지가 섞인 본문에서 정확한 글자만 바뀌고 나머지는 그대로다", () => {
    const out = linkifySource(SAMPLE_CONTENT, sampleLinks());
    expect(out).toContain("# 시작 😀");
    expect(out).toContain("[둘째](ac-wiki:");
    expect(out).toContain("🙂🙂");
    expect(out).not.toContain("[[둘째 페이지]]");
    expect(out).not.toContain("((없는곳))");
    expect(out.endsWith("끝 ↗ [밖](ac-wiki:" + sampleLinks()[3]!.start + ").\n")).toBe(true);
    // 링크 밖 글자 개수가 보존된다: 치환 조각을 빼고 보면 원문과 같다
    const stripped = out.replace(/\[[^\]]*\]\(ac-wiki:\d+\)/g, "§");
    expect(stripped).toBe(SAMPLE_CONTENT.replace(/\[\[둘째 페이지\]\]|\(\(없는곳\)\)|\{\{x:열기\}\}|<밖>/g, "§"));
  });
  it("start 내림차순 치환이라 앞쪽 범위가 밀리지 않는다 (입력 순서와 무관)", () => {
    const shuffled = [...sampleLinks()].reverse();
    expect(linkifySource(SAMPLE_CONTENT, shuffled)).toBe(linkifySource(SAMPLE_CONTENT, sampleLinks()));
  });
  it("이모지 바로 뒤·앞 링크", () => {
    const c = "😀[[a]]😀";
    expect(linkifySource(c, [link(2, 7, { label: "에이" })])).toBe("😀[에이](ac-wiki:2)😀");
  });
  it("겹치는 범위는 앞의 것만, 본문 밖·빈 범위·소수는 버린다", () => {
    const c = "0123456789";
    const out = usableLinks(c, [link(2, 6), link(4, 8), link(8, 9), link(9, 99), link(5, 5), link(1.5, 3), link(-1, 2)]);
    expect(out.map((l) => [l.start, l.end])).toEqual([[2, 6], [8, 9]]);
  });
  it("글자는 label → 해석된 제목 → target → 원문 조각, 깨질 글자는 이스케이프", () => {
    const c = "x [[a]] y";
    expect(linkLabel(link(2, 7, { label: "" , resolved: "p", target: "t" }), c, () => "제목")).toBe("제목");
    expect(linkLabel(link(2, 7, { label: "", target: "t" }), c)).toBe("t");
    expect(linkLabel(link(2, 7, { label: "", target: null }), c)).toBe("[[a]]");
    expect(linkLabel(link(2, 7, { label: "줄\n바꿈  공백" }), c)).toBe("줄 바꿈 공백");
    expect(escapeLinkText("a[b]\\c*d_e`f<g")).toBe("a\\[b\\]\\\\c\\*d\\_e\\`f\\<g");
  });
  it("hrefOf로 주소를 바꾸고 공백·괄호가 있으면 <>로 감싼다", () => {
    expect(linkifySource("[[a]]", [link(0, 5, { label: "A" })], { hrefOf: (l) => `/p/${l.start} x` })).toBe("[A](</p/0 x>)");
  });
  it("href 되읽기", () => {
    expect(parseLinkHref("ac-wiki:12")).toBe(12);
    expect(parseLinkHref("https://x")).toBeNull();
    expect(parseLinkHref("ac-wiki:x")).toBeNull();
    expect(parseLinkHref(undefined)).toBeNull();
  });
  it("편집기 장식은 같은 UTF-16 범위와 상태를 달고, 상태가 비면 unknown", () => {
    const marks = linkMarks(SAMPLE_CONTENT, [...sampleLinks(), link(0, 1, { status: "" })]);
    expect(marks).toHaveLength(5);
    const m = marks.find((x) => x.attrs?.["data-wiki-status"] === "broken")!;
    expect(SAMPLE_CONTENT.slice(m.from, m.to)).toBe("((없는곳))");
    expect(marks[0]!.attrs?.["data-wiki-status"]).toBe("unknown");
  });
});

describe("splitByMarks — 검색 강조 (UTF-16)", () => {
  const text = "앞 😀 한글검색어 뒤 🙂";
  it("한글 범위", () => {
    const s = text.indexOf("한글검색어");
    expect(splitByMarks(text, [{ start: s, end: s + 5 }])).toEqual([
      { text: "앞 😀 ", marked: false },
      { text: "한글검색어", marked: true },
      { text: " 뒤 🙂", marked: false },
    ]);
  });
  it("이모지(서로게이트 쌍) 한가운데 경계는 쌍 전체로 넓힌다", () => {
    const i = text.indexOf("😀");
    expect(splitByMarks(text, [{ start: i + 1, end: i + 2 }]).find((x) => x.marked)?.text).toBe("😀");
    expect(splitByMarks(text, [{ start: i, end: i + 1 }]).find((x) => x.marked)?.text).toBe("😀");
  });
  it("겹침 합치기·범위 밖·빈 범위·marks 없음", () => {
    expect(splitByMarks("abcdef", [{ start: 1, end: 3 }, { start: 2, end: 5 }, { start: 9, end: 12 }, { start: 3, end: 3 }])).toEqual([
      { text: "a", marked: false }, { text: "bcde", marked: true }, { text: "f", marked: false },
    ]);
    expect(splitByMarks("abc", undefined)).toEqual([{ text: "abc", marked: false }]);
    expect(splitByMarks("", [{ start: 0, end: 2 }])).toEqual([]);
  });
});

describe("buildTree", () => {
  const pages = samplePages();
  it("폴더 먼저, 숫자 정렬(2 < 10), 접힌 폴더는 자식을 숨긴다", () => {
    const rows = buildTree(pages, { expanded: new Set(), titleMode: "title" });
    expect(rows.map((r) => `${r.kind}:${r.key}`)).toEqual(["folder:deep", "folder:notes", "page:index", "page:lonely"]);
    expect(rows.filter((r) => r.kind === "folder").map((r) => r.key)).toEqual(["deep", "notes"]);
    const open = buildTree(pages, { expanded: new Set(["notes"]) });
    const names = open.filter((r) => r.depth === 1 && r.key.startsWith("notes/")).map((r) => r.name);
    expect(names).toEqual(["둘째", "첫째", "페이지 2", "페이지 10"]);
  });
  it("선택한 페이지의 상위 폴더는 항상 펼친다", () => {
    const rows = buildTree(pages, { expanded: new Set(), revealPath: "deep/er/x" });
    expect(rows.map((r) => r.key)).toContain("deep/er/x");
  });
  it("거르기는 맞는 페이지와 상위 폴더만 남기고 모두 펼친다", () => {
    const rows = buildTree(pages, { expanded: new Set(), filter: "페이지 10" });
    expect(rows.map((r) => r.key)).toEqual(["notes", "notes/page10"]);
  });
  it("제목 모드/경로 모드 이름과 폴더 헬퍼", () => {
    expect(buildTree(pages, { expanded: new Set(["notes"]), titleMode: "path" }).find((r) => r.key === "notes/page2")?.name).toBe("page2");
    expect(ancestorFolders("a/b/c")).toEqual(["a", "a/b"]);
    expect(allFolders(pages).sort()).toEqual(["deep", "deep/er", "notes"]);
  });
});

describe("그래프 순수 함수", () => {
  it("graphToFlow: 경로 순 정렬(결정론), 노드 종류는 서버 필드에서만, 쌍 엣지는 휨", () => {
    const g = sampleGraph();
    const a = graphToFlow(g, { centerPath: "a" });
    const b = graphToFlow({ ...g, nodes: [...(g.nodes ?? [])].reverse() }, { centerPath: "a" });
    expect(a.nodes.map((n) => n.id)).toEqual(["a", "b", "c", "d", "e"]);
    expect(b.nodes.map((n) => n.id)).toEqual(a.nodes.map((n) => n.id));
    expect(a.nodes.find((n) => n.id === "a")?.data).toMatchObject({ center: true, home: true });
    expect(a.nodes.find((n) => n.id === "c")?.data.broken).toBe(true);
    expect(a.nodes.find((n) => n.id === "e")?.data.scheme).toBe("x");
    const ab = a.edges.find((e) => e.source === "a" && e.target === "b")!;
    const ba = a.edges.find((e) => e.source === "b" && e.target === "a")!;
    expect(ab.data).toMatchObject({ paired: true, count: 3, touchesCenter: true });
    expect(ab.data.bend).toBe(-ba.data.bend);
    expect(a.edges.find((e) => e.target === "d")?.data).toMatchObject({ paired: false, bend: 0, touchesCenter: false });
  });
  it("모르는 노드를 가리키는 엣지와 중복 노드는 버린다", () => {
    const f = graphToFlow({ nodes: [{ path: "x" }, { path: "x" }], edges: [{ from: "x", to: "nope" }] });
    expect(f.nodes).toHaveLength(1);
    expect(f.edges).toHaveLength(0);
  });
  it("elk stress 배치: 옵션(stress, 시드, 간격)을 넘기고 같은 입력은 같은 결과", async () => {
    const layout = vi.fn(async (graph: unknown) => ({ children: (graph as { children: Array<{ id: string }> }).children.map((c, i) => ({ id: c.id, x: i * 10, y: 0 })) }));
    const engine = createElkGraphLayout(async () => ({ layout }));
    const f = graphToFlow(sampleGraph());
    const input = { nodes: f.nodes, edges: f.edges, gap: 48 };
    const r1 = await engine(input);
    const r2 = await engine(input);
    expect(r1).toEqual(r2);
    const sent = layout.mock.calls[0]![0] as { layoutOptions: Record<string, string> };
    expect(sent.layoutOptions["elk.algorithm"]).toBe("stress");
    expect(sent.layoutOptions["elk.randomSeed"]).toBe("1");
    expect(sent.layoutOptions["elk.spacing.nodeNode"]).toBe("48");
  });
  it("격자 배치는 결정론적", () => {
    const nodes = [1, 2, 3, 4, 5].map((i) => ({ id: String(i), width: 10, height: 10 }));
    expect(gridPositions(nodes, 2)["5"]).toEqual({ x: 12, y: 12 });
  });
  it("방향키: 그 방향 부채꼴 안에서 가장 가까운 노드, 없으면 null", () => {
    const c = [{ id: "m", x: 0, y: 0 }, { id: "r1", x: 100, y: 10 }, { id: "r2", x: 50, y: 5 }, { id: "d", x: 0, y: 80 }, { id: "far", x: 300, y: 0 }];
    expect(nearestNode(c, "m", "right")).toBe("r2");
    expect(nearestNode(c, "m", "down")).toBe("d");
    expect(nearestNode(c, "m", "up")).toBeNull();
    expect(nearestNode(c, "m", "left")).toBeNull();
    expect(nearestNode(c, "none", "left")).toBeNull();
  });
  it("엣지 선: 경계에서 4px 띄운 시작·끝, 쌍은 곡선", () => {
    const a = { x: 0, y: 0, width: 100, height: 40 };
    const b = { x: 300, y: 0, width: 100, height: 40 };
    const straight = edgeGeometry(a, b, 0);
    expect(straight.start).toEqual({ x: 104, y: 20 });
    expect(straight.end).toEqual({ x: 296, y: 20 });
    expect(straight.path.startsWith("M")).toBe(true);
    expect(straight.path).toContain("L");
    const bent = edgeGeometry(a, b, 1);
    expect(bent.path).toContain("Q");
    expect(edgeGeometry(a, b, -1).mid.y).toBeLessThan(20 + 1e-9 + 100);
    expect(bent.mid.y).not.toBe(straight.mid.y);
  });
});

describe("표시 표 — 열린 문자열", () => {
  const display = { ops: { a: { label: "에이", tone: "success" } }, authorKinds: { user: { label: "사람" } } };
  it("표에 있으면 라벨·톤, 없으면 원문 + 중립", () => {
    expect(resolveDisplay(display.ops, "a")).toMatchObject({ label: "에이", tone: "success", known: true });
    expect(resolveDisplay(display.ops, "zzz")).toMatchObject({ label: "zzz", tone: "neutral", known: false });
    expect(resolveDisplay(undefined, "q")).toMatchObject({ label: "q", tone: "neutral" });
    expect(resolveDisplay({ x: { tone: "<script>" } }, "x").tone).toBe("neutral");
    // 프로토타입 키
    expect(resolveDisplay(display.ops, "constructor").known).toBe(false);
  });
  it("쓴 주체 이름 = label → agent_id → 종류 표시 → 종류 원문", () => {
    expect(authorLabel({ kind: "agent", label: "이름", agent_id: "id" }, display)).toBe("이름");
    expect(authorLabel({ kind: "agent", label: "", agent_id: "id" }, display)).toBe("id");
    expect(authorLabel({ kind: "user" }, display)).toBe("사람");
    expect(authorLabel({ kind: "robot" }, display)).toBe("robot");
  });
  it("심각도 순서: 모르는 값은 뒤", () => {
    const order = ["error", "warning"];
    expect(severityRank("error", order)).toBe(0);
    expect(severityRank("purple", order)).toBe(2);
  });
  it("상대 시각 문구는 messages 표에서", () => {
    expect(formatRelative(SAMPLE_NOW - 10, SAMPLE_NOW, defaultMessages)).toBe("방금");
    expect(formatRelative(SAMPLE_NOW - 7200, SAMPLE_NOW, defaultMessages)).toBe("2시간 전");
    expect(formatRelative(SAMPLE_NOW - 86_400 * 3, SAMPLE_NOW, defaultMessages)).toBe("3일 전");
    expect(formatRelative(SAMPLE_NOW + 50, SAMPLE_NOW, defaultMessages)).toBe("방금");
  });
});
