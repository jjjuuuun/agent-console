import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { WikiGraph, WikiIssue, WikiLintReport } from "@agent-console/contracts/wiki";
import { LONG, SYNTAX, project, projectView, setup, wikiSummary, wikiView } from "./wikiTestSetup";
import { filterGraph } from "./GraphTab";
import { collectEnumUi } from "./rulesSchema";
import { getContractSchema } from "@agent-console/contracts";

// 그래프 캔버스(React Flow)는 레이아웃 API가 필요해 간단한 대역으로 바꾼다(캔버스 자체는 wiki-view 시험이 확인).
vi.mock("@agent-console/wiki-view", async (orig) => {
  const actual = await orig<typeof import("@agent-console/wiki-view")>();
  return {
    ...actual,
    LinkGraph: (p: { graph: WikiGraph; centerPath?: string | null; onOpen?: (n: { path: string; broken: boolean; scheme: string | null }) => void; onCenter?: (path: string) => void }) => (
      <div data-testid="graph-stub" data-center={p.centerPath ?? ""} data-nodes={(p.graph.nodes ?? []).length}>
        {(p.graph.nodes ?? []).map((n) => (
          <span key={n.path}>
            <button type="button" onClick={() => p.onOpen?.({ path: n.path, broken: n.broken === true, scheme: n.scheme ?? null })}>{`열기 ${n.path}`}</button>
            <button type="button" onClick={() => p.onCenter?.(n.path)}>{`중심 ${n.path}`}</button>
          </span>
        ))}
      </div>
    ),
  };
});

afterEach(cleanup);

const apiError = (status: number, code: string) => new ApiError(status, { code, message: "서버 문장", details: {} });
const GRAPH: WikiGraph = {
  nodes: [
    { path: "a/one", title: "하나" },
    { path: "a/two", title: "둘" },
    { path: "a/gone", title: "없는", broken: true },
  ],
  edges: [
    { from: "a/one", to: "a/two", count: 2 },
    { from: "a/one", to: "a/gone", count: 1 },
  ],
  truncated: false,
};
const base = (tab: string, extra = "") => `/wiki/w1?prj=p1&tab=${tab}${extra}`;
const fixture = (over: Record<string, unknown> = {}) => ({ wikis: [wikiSummary({ pages: 3 })], syntax: SYNTAX, ...over });

describe("그래프 탭", () => {
  it("중심 기본값은 위키 home이고 깊이 1로 서버 그래프를 받아 노드 수를 보인다", async () => {
    const getWikiGraph = vi.fn(async () => GRAPH);
    const { wiki } = setup(base("graph"), fixture({ view: wikiView({ home: "a/one" }), wiki: { getWikiGraph } }));
    const stub = await screen.findByTestId("graph-stub", {}, LONG);
    expect(stub.getAttribute("data-center")).toBe("a/one");
    expect(wiki.getWikiGraph).toHaveBeenCalledWith("w1", { center: "a/one", depth: 1 });
    expect(screen.getByText("노드 3개")).toBeTruthy();
  });

  it("잘렸으면 서버 총 개수로 안내하고, 총 개수가 없으면 지어내지 않는다", async () => {
    const first = setup(base("graph"), fixture({ wiki: { getWikiGraph: vi.fn(async () => ({ ...GRAPH, truncated: true, total: 900 })) } }));
    expect(await screen.findByText("900개 중 3개만 보입니다", {}, LONG)).toBeTruthy();
    first.unmount();
    cleanup();
    setup(base("graph"), fixture({ wiki: { getWikiGraph: vi.fn(async () => ({ ...GRAPH, truncated: true })) } }));
    expect(await screen.findByText("일부만 보입니다. 깊이를 줄이세요", {}, LONG)).toBeTruthy();
  });

  it("전체를 고르면 center= 가 빈 값으로 주소에 남고 깊이 선택이 꺼진다", async () => {
    const { router, wiki } = setup(base("graph"), fixture({ wiki: { getWikiGraph: vi.fn(async () => GRAPH) } }));
    await screen.findByTestId("graph-stub", {}, LONG);
    fireEvent.change(screen.getByLabelText("중심"), { target: { value: "all" } });
    await waitFor(() => expect(router.state.location.search).toContain("center="), LONG);
    await waitFor(() => expect(wiki.getWikiGraph).toHaveBeenLastCalledWith("w1", {}), LONG);
    expect((screen.getByRole("button", { name: "2" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("깊이를 누르면 주소 depth가 바뀌고 서버에 그 깊이로 다시 묻는다", async () => {
    const { router, wiki } = setup(base("graph", "&center=a/one"), fixture({ wiki: { getWikiGraph: vi.fn(async () => GRAPH) } }));
    await screen.findByTestId("graph-stub", {}, LONG);
    fireEvent.click(screen.getByRole("button", { name: "2" }));
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("depth")).toBe("2"), LONG);
    await waitFor(() => expect(wiki.getWikiGraph).toHaveBeenLastCalledWith("w1", { center: "a/one", depth: 2 }), LONG);
  });

  it("끊긴 대상 보기를 끄면 점선 노드와 닿은 선이 빠진다(재질의 없음)", async () => {
    const { wiki } = setup(base("graph", "&center=a/one"), fixture({ wiki: { getWikiGraph: vi.fn(async () => GRAPH) } }));
    await screen.findByTestId("graph-stub", {}, LONG);
    const calls = wiki.getWikiGraph.mock.calls.length;
    fireEvent.click(screen.getByLabelText("끊긴 대상 보기"));
    await waitFor(() => expect(screen.getByTestId("graph-stub").getAttribute("data-nodes")).toBe("2"), LONG);
    expect(wiki.getWikiGraph.mock.calls.length).toBe(calls);
  });

  it("노드 열기는 페이지 탭으로 가고, 끊긴 대상은 새 페이지 대화상자를 경로가 채워진 채 연다", async () => {
    const { router } = setup(base("graph", "&center=a/one"), fixture({ wiki: { getWikiGraph: vi.fn(async () => GRAPH) } }));
    await screen.findByTestId("graph-stub", {}, LONG);
    fireEvent.click(screen.getByRole("button", { name: "열기 a/gone" }));
    const dialog = await screen.findByRole("dialog", {}, LONG);
    expect((within(dialog).getByLabelText(/경로/) as HTMLInputElement).value).toBe("a/gone");
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    fireEvent.click(screen.getByRole("button", { name: "열기 a/two" }));
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("path")).toBe("a/two"), LONG);
    expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("page");
  });

  it("스킴 노드는 scheme_target이 있고 그 역할 화면이 켜져 있을 때만 열린다", async () => {
    const graph: WikiGraph = {
      nodes: [
        { path: "a/one", title: "하나" },
        { path: "run:r-1", title: "실행", scheme: "run", scheme_target: { role: "runs", id_from: "r-1", query: "tab={value}" } },
        { path: "x:y", title: "표 없음", scheme: "x" },
      ],
      edges: [],
      truncated: false,
    };
    const modules = [{ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: ["wiki", "projects", "settings", "runs"] }];
    const { router } = setup(base("graph", "&center=a/one"), fixture({ modules, wiki: { getWikiGraph: vi.fn(async () => graph) } }));
    await screen.findByTestId("graph-stub", {}, LONG);
    fireEvent.click(screen.getByRole("button", { name: "열기 x:y" }));
    expect(router.state.location.pathname).toBe("/wiki/w1");
    fireEvent.click(screen.getByRole("button", { name: "열기 run:r-1" }));
    await waitFor(() => expect(router.state.location.pathname).toMatch(/\/r-1$/), LONG);
    expect(router.state.location.search).toBe("?tab=r-1&prj=p1");
  });

  it("중심 페이지가 없으면 전체로 되돌리고 안내한다", async () => {
    const getWikiGraph = vi.fn(async (_w: string, q?: { center?: string }) => (q?.center === undefined ? GRAPH : { nodes: [{ path: "x", broken: true }], edges: [], truncated: false }));
    setup(base("graph", "&center=nope"), fixture({ wiki: { getWikiGraph } }));
    expect(await screen.findByTestId("wiki-graph-center-missing", {}, LONG)).toBeTruthy();
    expect(screen.getByText("‘nope’ 페이지가 없어 전체를 보입니다")).toBeTruthy();
  });

  it("페이지가 0개면 비었다는 안내, 링크 문법이 없으면 그래프 대신 문법 없음 본문과 [규칙 열기]", async () => {
    const empty = setup(base("graph"), fixture({ wikis: [wikiSummary({ pages: 0 })], wiki: { getWikiGraph: vi.fn(async () => ({ nodes: [], edges: [] })) } }));
    expect(await screen.findByTestId("wiki-graph-empty", {}, LONG)).toBeTruthy();
    empty.unmount();
    cleanup();
    const { router } = setup(base("graph"), fixture({ syntax: { syntax: { links: [] }, sources: {}, empty: true }, wiki: { getWikiGraph: vi.fn(async () => GRAPH) } }));
    const note = await screen.findByTestId("wiki-graph-nosyntax", {}, LONG);
    expect(within(note).getByText("링크 문법이 없습니다")).toBeTruthy();
    fireEvent.click(within(note).getByRole("button", { name: "규칙 열기" }));
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("rules"), LONG);
    expect(screen.queryByTestId("graph-stub")).toBeNull();
  });

  it("오류는 오류 블록과 다시 시도", async () => {
    setup(base("graph"), fixture({ wiki: { getWikiGraph: vi.fn(async () => { throw apiError(500, "뭔가"); }) } }));
    expect(await screen.findByRole("button", { name: "다시 시도" }, LONG)).toBeTruthy();
  });

  it("filterGraph: 고아 표시를 끄면 고아 표시만 빠지고 노드는 그대로다", () => {
    const g: WikiGraph = { nodes: [{ path: "a", orphan: true }, { path: "b" }], edges: [] };
    expect(filterGraph(g, true, false).nodes?.map((n) => n.orphan)).toEqual([false, undefined]);
    expect(filterGraph(g, true, true).nodes?.map((n) => n.orphan)).toEqual([true, undefined]);
  });
});

const ISSUES: WikiIssue[] = [
  { severity: "warning", code: "broken_link", message: "‘재시도’ 페이지가 없습니다", path: "a/two", details: { line: 12 } },
  { severity: "info", code: "orphan", message: "어디서도 링크되지 않았습니다", path: "a/one" },
  { severity: "purple" as unknown as WikiIssue["severity"], code: "zz_custom", message: "서버만 아는 점검", path: "a/three", details: { rule_id: "r-임의" } },
];
const REPORT: WikiLintReport = { issues: ISSUES, pages: 3, generated_at: 1_700_000_000, counts: { warning: 1, info: 1, purple: 1 } };

describe("점검 탭", () => {
  it("서버 점검 결과를 표로 보이고 모르는 코드·심각도는 원문으로 보인다", async () => {
    setup(base("lint"), fixture({ wiki: { getWikiLint: vi.fn(async () => REPORT) } }));
    const grid = await screen.findByRole("grid", {}, LONG);
    expect(within(grid).getByText("zz_custom")).toBeTruthy();
    expect(within(grid).getByText("purple")).toBeTruthy();
    expect(within(grid).getByText("r-임의")).toBeTruthy();
    expect(screen.getByText("점검한 페이지 3개")).toBeTruthy();
  });

  it("행을 열면 그 페이지의 그 줄로 간다", async () => {
    const { router } = setup(base("lint"), fixture({ wiki: { getWikiLint: vi.fn(async () => REPORT) } }));
    const grid = await screen.findByRole("grid", {}, LONG);
    fireEvent.click(within(grid).getAllByRole("row").find((r) => r.textContent?.includes("재시도")) as HTMLElement);
    fireEvent.keyDown(grid, { key: "Enter" });
    await waitFor(() => expect(router.state.location.search).toContain("line=12"), LONG);
    expect(new URLSearchParams(router.state.location.search).get("path")).toBe("a/two");
  });

  it("심각도·코드 거르기가 주소(sev·code·q)에 남고 주소에서 되살아난다", async () => {
    const { router } = setup(base("lint"), fixture({ wiki: { getWikiLint: vi.fn(async () => REPORT) } }));
    await screen.findByRole("grid", {}, LONG);
    fireEvent.change(screen.getByLabelText("코드 거르기"), { target: { value: "orphan" } });
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("code")).toBe("orphan"), LONG);
    cleanup();
    setup(base("lint", "&code=orphan"), fixture({ wiki: { getWikiLint: vi.fn(async () => REPORT) } }));
    await screen.findByRole("grid", {}, LONG);
    await waitFor(() => expect(within(screen.getByRole("grid")).queryByText("zz_custom")).toBeNull(), LONG);
  });

  it("[다시 점검]은 다시 읽기(scan) 뒤 점검을 다시 받는다", async () => {
    const getWikiLint = vi.fn(async () => REPORT);
    const { wiki } = setup(base("lint"), fixture({ wiki: { getWikiLint, scanWiki: vi.fn(async () => ({})) } }));
    await screen.findByRole("grid", {}, LONG);
    const before = getWikiLint.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "다시 점검" }));
    await waitFor(() => expect(wiki.scanWiki).toHaveBeenCalledWith("w1"), LONG);
    await waitFor(() => expect(getWikiLint.mock.calls.length).toBeGreaterThan(before), LONG);
  });

  it("이슈가 없으면 문제 없음, 켜진 점검이 하나도 없으면 안내와 [규칙 열기]", async () => {
    setup(base("lint"), fixture({ wiki: { getWikiLint: vi.fn(async () => ({ issues: [] })) } }));
    expect(await screen.findByText("문제가 없습니다", {}, LONG)).toBeTruthy();
    cleanup();
    setup(base("lint"), fixture({ syntax: { syntax: { links: [] }, sources: {}, empty: true }, wiki: { getWikiLint: vi.fn(async () => ({ issues: [] })) } }));
    expect(await screen.findByTestId("wiki-lint-none-enabled", {}, LONG)).toBeTruthy();
  });

  it("partial이면 점검하지 못했다는 띠와 skipped 페이지 링크가 나오고, 누르면 그 페이지로 간다", async () => {
    const { router } = setup(base("lint"), fixture({ wiki: { getWikiLint: vi.fn(async () => ({ ...REPORT, partial: true, skipped: ["a/bad", "z/x"] })) } }));
    const band = await screen.findByTestId("wiki-lint-partial", {}, LONG);
    expect(band.textContent).toContain("일부 페이지를 점검하지 못했습니다");
    expect(band.textContent).toContain("점검하지 못한 페이지 2개");
    fireEvent.click(within(band).getByRole("button", { name: "점검하지 못한 페이지 열기: a/bad" }));
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("path")).toBe("a/bad"), LONG);
  });

  it("partial이 아니면 띠가 없고, enabled_checks는 이름을 계약 상수·표시 표에서 찾아 문장으로 보인다", async () => {
    setup(base("lint"), fixture({ wiki: { getWikiLint: vi.fn(async () => ({ ...REPORT, partial: false, enabled_checks: ["broken_link", "lint_rules", "write_rules", "zz_new"] })) } }));
    const line = await screen.findByTestId("wiki-lint-enabled", {}, LONG);
    expect(line.textContent).toMatch(/^켜진 점검: .+, 점검 규칙, 쓰기 규칙 다시 보기, zz_new$/);
    expect(screen.queryByTestId("wiki-lint-partial")).toBeNull();
  });

  it("enabled_checks가 null(옛 서버)이면 문장을 지어내지 않는다", async () => {
    setup(base("lint"), fixture({ wiki: { getWikiLint: vi.fn(async () => ({ ...REPORT, enabled_checks: null })) } }));
    await screen.findByRole("grid", {}, LONG);
    expect(screen.queryByTestId("wiki-lint-enabled")).toBeNull();
  });

  it("문법이 없어도 다른 이슈는 보이고 표 위에 링크 점검 안내가 붙는다", async () => {
    setup(base("lint"), fixture({ syntax: { syntax: { links: [] }, sources: {}, empty: true }, wiki: { getWikiLint: vi.fn(async () => REPORT) } }));
    expect(await screen.findByTestId("wiki-lint-nosyntax", {}, LONG)).toBeTruthy();
    expect(within(screen.getByRole("grid")).getByText("zz_custom")).toBeTruthy();
  });
});

const RULE_A = { id: "ra", name: "규칙 가" };
const RULE_B = { id: "rb", name: "규칙 나" };
const rulesView = (ids: string[]) =>
  wikiView(
    { rules: ids },
    {
      rules: {
        rules: ids.map((id) => ({ id, name: id === "ra" ? "규칙 가" : id === "rb" ? "규칙 나" : id, ...(id === "gone" ? { missing: true } : {}) })),
        instructions: "## 규칙 가\n이렇게 씁니다",
        entries: [
          { kind: "write", id: "w-1", rule_id: "ra", label: "금지된 글", action: "reject" },
          { kind: "write", id: "w-2", rule_id: "rb", label: "경고만", action: "zap" },
          { kind: "lint", id: "l-1", rule_id: "ra", label: "오래됨", severity: "warning" },
          { kind: "template", id: "t-1", rule_id: "rb", label: "결정" },
        ],
        write_rules: 2,
        lint_rules: 1,
        page_templates: 1,
      },
    },
  );
const rulesFixture = (ids: string[], over: Record<string, unknown> = {}) =>
  fixture({
    view: rulesView(ids),
    modules: [{ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: ["wiki", "projects", "settings", "wiki:rules"] }],
    info: { pages_root: ".cfg/wikis", capabilities: { history: true, search: true, runs: true, rules_library: false, import_export: true }, limits: { max_page_bytes: 1, max_pages: 1, graph_max_nodes: 1 } },
    wiki: {
      listWikiRules: vi.fn(async () => [
        { ...RULE_A, counts: { write: 1, lint: 1, templates: 0 }, has_instructions: true },
        { ...RULE_B, counts: { write: 1, lint: 0, templates: 1 } },
      ]),
      ...((over["wiki"] as object | undefined) ?? {}),
    },
    ...Object.fromEntries(Object.entries(over).filter(([k]) => k !== "wiki")),
  });

describe("규칙 탭", () => {
  it("쓰는 규칙 순서를 바꿔 저장하면 위키 정의 전체를 If-Match(정의 버전)와 함께 PUT 한다", async () => {
    const putWiki = vi.fn(async (_w: string, body: unknown) => ({ value: wikiView((body as { rules: string[] }).rules ? { rules: (body as { rules: string[] }).rules } : {}), version_hash: "wv2" }));
    const { wiki } = setup(base("rules"), rulesFixture(["ra", "rb"], { wiki: { putWiki } }));
    const down = await screen.findByRole("button", { name: /규칙 가 아래로/ }, LONG);
    fireEvent.click(down);
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(wiki.putWiki).toHaveBeenCalledTimes(1), LONG);
    const [id, body, hash] = putWiki.mock.calls[0] as unknown as [string, { rules: string[]; name: string }, string];
    expect(id).toBe("w1");
    expect(hash).toBe("wv1");
    expect(body.rules).toEqual(["rb", "ra"]);
    expect(body.name).toBe("노트");
  });

  it("규칙을 빼면 되돌리기 토스트가 나오고 누르면 목록이 돌아온다", async () => {
    setup(base("rules"), rulesFixture(["ra", "rb"]));
    fireEvent.click(await screen.findByRole("button", { name: "규칙 가 빼기" }, LONG));
    fireEvent.click(await screen.findByRole("button", { name: "되돌리기" }, LONG));
    expect(await screen.findByRole("button", { name: "규칙 가 빼기" }, LONG)).toBeTruthy();
  });

  it("충돌(412)이면 충돌 배너가 나오고 저장을 다시 시도하지 않는다", async () => {
    const putWiki = vi.fn(async () => { throw apiError(412, "version_conflict"); });
    setup(base("rules"), rulesFixture(["ra", "rb"], { wiki: { putWiki } }));
    fireEvent.click(await screen.findByRole("button", { name: /규칙 가 아래로/ }, LONG));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByTestId("wiki-rules-conflict", {}, LONG)).toBeTruthy();
    expect(putWiki).toHaveBeenCalledTimes(1);
  });

  it("합친 지침과 합친 규칙 표를 서버 값 그대로 보이고, 모르는 동작은 원문 + 중립이다", async () => {
    setup(base("rules"), rulesFixture(["ra", "rb"]));
    const pre = await screen.findByLabelText("합친 지침", { selector: "pre" }, LONG);
    expect(pre.textContent).toContain("이렇게 씁니다");
    expect(screen.getByText("금지된 글")).toBeTruthy();
    expect(screen.getByText("zap")).toBeTruthy();
    expect(screen.getByRole("table", { name: "쓰기 규칙" })).toBeTruthy();
  });

  it("합친 규칙 표에 applies_to·경로 틀·표시 이름 열이 있고 null 칸은 비어 있다", async () => {
    const view = rulesView(["ra"]);
    const entries = [
      { kind: "write", id: "w-all", rule_id: "ra", label: "전부", action: "reject", applies_to: [] },
      { kind: "write", id: "w-glob", rule_id: "ra", label: "글롭", action: "reject", applies_to: ["a/**", "b/*.md"] },
      { kind: "write", id: "w-old", rule_id: "ra", label: "옛 서버", action: "reject", applies_to: null },
      { kind: "template", id: "t-1", rule_id: "ra", label: "t-1", path: "d/{slug}", title: "결정" },
      { kind: "template", id: "t-2", rule_id: "ra", label: "t-2", path: null, title: null },
    ];
    setup(base("rules"), { ...rulesFixture(["ra"]), view: { ...view, rules: { ...view.rules, entries } as never } });
    const write = await screen.findByRole("table", { name: "쓰기 규칙" }, LONG);
    expect(within(write).getByRole("columnheader", { name: "적용 경로" })).toBeTruthy();
    const rowOf = (t: HTMLElement, id: string) => within(t).getAllByText(id)[0]!.closest("tr") as HTMLElement;
    expect(within(rowOf(write, "w-all")).getByText("모든 페이지")).toBeTruthy();
    expect(within(rowOf(write, "w-glob")).getByText("a/**, b/*.md")).toBeTruthy();
    expect(within(rowOf(write, "w-old")).queryByText("모든 페이지")).toBeNull();
    const tpl = screen.getByRole("table", { name: "페이지 틀" });
    expect(within(tpl).getByRole("columnheader", { name: "경로 틀" })).toBeTruthy();
    expect(within(tpl).getByRole("columnheader", { name: "표시 이름" })).toBeTruthy();
    expect(within(rowOf(tpl, "t-1")).getByText("d/{slug}")).toBeTruthy();
    expect(within(rowOf(tpl, "t-1")).getByText("결정")).toBeTruthy();
    const empty = rowOf(tpl, "t-2").querySelectorAll("td");
    expect(empty[1]?.textContent).toBe("t-2");
    expect(empty[2]?.textContent).toBe("");
    expect(empty[3]?.textContent).toBe("");
  });

  it("스키마의 x-ui.enum_tones·enum_labels가 동작 칩의 톤·라벨이 된다", async () => {
    setup(base("rules"), rulesFixture(["ra", "rb"]));
    const { labels, tones } = collectEnumUi(getContractSchema("WikiRulesDefinition"));
    const chip = await screen.findByText(labels["reject"] as string, {}, LONG);
    expect(chip.closest("[data-tone]")?.getAttribute("data-tone")).toBe(tones["reject"]);
  });

  it("규칙이 공간에 없으면 danger 행이 나오고 규칙이 0개면 정보 안내가 나온다", async () => {
    setup(base("rules"), rulesFixture(["gone"]));
    expect(await screen.findByText(/‘gone’ 규칙이 이 프로젝트에 없습니다/, {}, LONG)).toBeTruthy();
    cleanup();
    setup(base("rules"), { ...rulesFixture([]), view: wikiView({ rules: [] }) });
    expect(await screen.findByText(/쓰는 규칙이 없습니다/, {}, LONG)).toBeTruthy();
    expect(screen.getByText("규칙이 없어 비어 있습니다")).toBeTruthy();
  });

  it("실행 연동이 꺼져 있으면 지침 위에 안내가 붙는다", async () => {
    setup(base("rules"), { ...rulesFixture(["ra"]), info: { pages_root: ".cfg", capabilities: { history: true, search: true, runs: false, rules_library: false, import_export: false }, limits: { max_page_bytes: 1, max_pages: 1, graph_max_nodes: 1 } } });
    expect(await screen.findByTestId("wiki-rules-runs-off", {}, LONG)).toBeTruthy();
  });

  it("읽기 전용 폴더(WikiInfo.writable=false)에서는 저장이 aria-disabled이고 맨 위 경고가 있다", async () => {
    setup(base("rules"), { ...rulesFixture(["ra"]), info: { pages_root: ".cfg", capabilities: { history: true, search: true, runs: true, rules_library: false, import_export: false }, limits: { max_page_bytes: 1, max_pages: 1, graph_max_nodes: 1 }, writable: false } });
    expect(await screen.findByTestId("wiki-rules-readonly", {}, LONG)).toBeTruthy();
    expect(screen.getByRole("button", { name: "저장" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("유효 문법 값 트리에 출처 배지가 있고 규칙 출처는 규칙 화면으로 이어진다", async () => {
    const { router } = setup(base("rules"), {
      ...rulesFixture(["ra"]),
      syntax: { syntax: { links: [{ id: "r1", kind: "k1", pattern: "x" }] }, sources: { "/links": "rules:ra" }, empty: false },
    });
    const tree = await screen.findByLabelText("링크 규칙", {}, LONG);
    fireEvent.click(within(tree).getByRole("button", { name: "열기" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/wiki-rules/ra"), LONG);
    expect(router.state.location.search).toContain("prj=p1");
  });

  it("프로젝트 0개에서도 규칙 탭이 있는 위키 화면은 읽기 요청만으로 그려진다", async () => {
    setup(base("rules"), { ...rulesFixture(["ra"]), projects: [projectView(project("p1", { name: "결제앱" }))] });
    expect(await screen.findByTestId("wiki-rules", {}, LONG)).toBeTruthy();
  });
});
