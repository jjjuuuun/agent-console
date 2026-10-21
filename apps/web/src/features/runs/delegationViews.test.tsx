import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { NodeRun, Run } from "@agent-console/contracts";
import { ChildRunsMenu, type ChildRunRow } from "./ChildRunsMenu";
import { EdgeJudgementView, type EdgeJudgementViewProps } from "./EdgeJudgementView";
import { NodeRunList } from "./NodeRunList";
import { nodeRunKey } from "./nodeRuns";
import { RunBreadcrumb } from "./RunBreadcrumb";

afterEach(cleanup);

describe("RunBreadcrumb", () => {
  const items = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `run-${i}-xxxxxx`, short: `r-${i}`, teamName: `팀${i}` }));
  it("루트 실행(체인 1개)이면 아무것도 그리지 않는다", () => {
    const { container } = render(<MemoryRouter><RunBreadcrumb items={items(1)} hrefOf={(id) => `/runs/${id}`} /></MemoryRouter>);
    expect(container.textContent).toBe("");
  });
  it("루트부터 현재까지 보이고, 앞 항목은 링크·마지막은 현재 위치, 팀 구성 이름이 아래에 붙는다", () => {
    render(<MemoryRouter><RunBreadcrumb items={items(3)} hrefOf={(id) => `/runs/${id}`} /></MemoryRouter>);
    const nav = screen.getByRole("navigation", { name: "실행 위치" });
    expect(within(nav).getByRole("link", { name: "루트 r-0" }).getAttribute("href")).toBe("/runs/run-0-xxxxxx");
    expect(within(nav).getByRole("link", { name: "r-1" })).toBeTruthy();
    expect(within(nav).queryByRole("link", { name: "r-2" })).toBeNull();
    expect(nav.querySelector("[aria-current='page']")?.textContent).toContain("r-2");
    expect(within(nav).getByText("팀1")).toBeTruthy();
  });
  it("5개를 넘으면 앞쪽을 … 메뉴로 접는다", () => {
    render(<MemoryRouter><RunBreadcrumb items={items(7)} hrefOf={(id) => `/runs/${id}`} /></MemoryRouter>);
    const nav = screen.getByRole("navigation", { name: "실행 위치" });
    const more = within(nav).getByRole("button", { name: "상위 단계" });
    expect(more.textContent).toBe("…");
    // 접힌 항목(앞 3개)은 눌러야 팝오버에 나오고, 보이는 항목은 4개 + 접기 버튼
    expect(nav.querySelectorAll(".dlg-crumb-fold li")).toHaveLength(0);
    expect(nav.querySelectorAll("ol > li")).toHaveLength(5);
    fireEvent.click(more);
    expect(nav.querySelectorAll(".dlg-crumb-fold li")).toHaveLength(3);
  });
});

describe("ChildRunsMenu", () => {
  const row = (id: string): ChildRunRow => ({ run: { id, status: "running" } as Run, teamName: "검토 파이프라인", nodeText: "검토 · 2회차", statusLabel: "실행 중", startedText: "방금", durationText: "3초" });
  it("자식이 0개면 컨트롤 자체가 없다", () => {
    const { container } = render(<ChildRunsMenu rows={[]} onOpen={() => {}} />);
    expect(container.textContent).toBe("");
  });
  it("단추를 열면 행 목록이 나오고 Enter로 열며 Esc로 닫고 단추로 돌아간다", () => {
    const onOpen = vi.fn();
    render(<ChildRunsMenu rows={[row("c1"), row("c2")]} onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: /자식 실행 2개/ });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    const items = screen.getAllByRole("menuitem");
    expect(items).toHaveLength(2);
    expect(items[0]!.textContent).toContain("검토 파이프라인 · 검토 · 2회차");
    fireEvent.keyDown(items[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1]!, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    fireEvent.click(screen.getAllByRole("menuitem")[1]!);
    expect(onOpen).toHaveBeenCalledWith("c2");
  });
});

describe("NodeRunList", () => {
  const mk = (n: number, extra: (i: number) => Partial<NodeRun> = () => ({})): NodeRun[] =>
    Array.from({ length: n }, (_, i) => ({ run_id: "r", node_id: "n", status: "succeeded", attempt: 1, iteration: i, call: 0, started_at: i + 1, duration_ms: 1000, ...extra(i) }) as NodeRun);
  const base = (runs: NodeRun[], selected = runs.length - 1, over: Record<string, unknown> = {}) => ({
    runs,
    selectedKey: nodeRunKey(runs[selected]!),
    onSelect: vi.fn(),
    statusLabel: (s: string) => `상태:${s}`,
    startedText: (r: NodeRun) => `t${r.started_at}`,
    callerLabel: () => undefined,
    ...over,
  });
  it("실행 열 문구(회차)와 선택·소요·호출자 열을 그린다", () => {
    const runs = mk(3, (i) => (i === 2 ? { invoked_by: ["pl"], call: 0 } : {}));
    render(<NodeRunList {...base(runs)} callerLabel={(r) => (r.invoked_by?.length ? "PL" : undefined)} />);
    const grid = screen.getByRole("grid", { name: "실행 목록" });
    const rows = within(grid).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("gridcell")[0]!.textContent)).toEqual(["1회차", "2회차", "3회차"]);
    expect(rows[2]!.getAttribute("aria-selected")).toBe("true");
    expect(within(rows[2]!).getByText("PL")).toBeTruthy();
    expect(within(grid).queryByText("자식 실행")).toBeNull();
  });
  it("자식 실행 열은 어떤 행에든 자식이 있을 때만 있고, 하나면 링크·여럿이면 n개", () => {
    const runs = mk(2);
    const onOpenChild = vi.fn();
    render(<NodeRunList {...base(runs)} childrenOf={(r) => (r.iteration === 0 ? [{ runId: "c1", short: "r-7c1b" }] : [{ runId: "c2", short: "a" }, { runId: "c3", short: "b" }])} onOpenChild={onOpenChild} />);
    expect(screen.getByRole("columnheader", { name: "자식 실행" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /r-7c1b/ }));
    expect(onOpenChild).toHaveBeenCalledWith("c1");
    expect(screen.getByText("2개 ▾")).toBeTruthy();
  });
  it("↑↓ Enter Home End로 움직이고 End는 최신으로 따라가기를 부른다", () => {
    const runs = mk(3);
    const p = base(runs, 1);
    const onLatest = vi.fn();
    render(<NodeRunList {...p} onLatest={onLatest} />);
    const row = (i: number) => document.querySelector<HTMLElement>(`[data-index='${i}']`)!;
    fireEvent.keyDown(row(1), { key: "ArrowDown" });
    expect(p.onSelect).toHaveBeenLastCalledWith(nodeRunKey(runs[2]!));
    fireEvent.keyDown(row(1), { key: "ArrowUp" });
    expect(p.onSelect).toHaveBeenLastCalledWith(nodeRunKey(runs[0]!));
    fireEvent.keyDown(row(1), { key: "Home" });
    expect(p.onSelect).toHaveBeenLastCalledWith(nodeRunKey(runs[0]!));
    fireEvent.keyDown(row(1), { key: "End" });
    expect(onLatest).toHaveBeenCalled();
    fireEvent.keyDown(row(1), { key: "Enter" });
    expect(p.onSelect).toHaveBeenLastCalledWith(nodeRunKey(runs[1]!));
  });
  it("경계에서 멈춘다(첫 행에서 ↑, 마지막 행에서 ↓는 같은 행)", () => {
    const runs = mk(2);
    const p = base(runs, 0);
    render(<NodeRunList {...p} />);
    fireEvent.keyDown(document.querySelector("[data-index='0']")!, { key: "ArrowUp" });
    expect(p.onSelect).toHaveBeenLastCalledWith(nodeRunKey(runs[0]!));
  });
  it("응답 대기 행에는 [상호작용 탭에서 답하기]", () => {
    const runs = mk(2, (i) => (i === 1 ? { status: "waiting" } : {}));
    const onAnswer = vi.fn();
    render(<NodeRunList {...base(runs)} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByRole("button", { name: "상호작용 탭에서 답하기" }));
    expect(onAnswer).toHaveBeenCalled();
    expect(screen.getByText("⏸ 응답 대기")).toBeTruthy();
  });
  it("50개를 넘으면 보이는 행만 그린다", () => {
    const runs = mk(120);
    render(<NodeRunList {...base(runs, 0)} />);
    const rendered = document.querySelectorAll("[data-index]").length;
    expect(rendered).toBeGreaterThan(0);
    expect(rendered).toBeLessThan(40);
    expect(screen.getByRole("grid").getAttribute("aria-rowcount")).toBe("121");
  });
});

describe("EdgeJudgementView", () => {
  const props = (extra: Partial<EdgeJudgementViewProps> = {}): EdgeJudgementViewProps => ({
    fromLabel: "검사",
    toLabel: "알림",
    kindTitle: "조건에 따라 지나감",
    chips: ["/output 포함 ‘PASS’"],
    status: "passed",
    statusTime: "14:02:11",
    passes: 1,
    operators: [{ id: "op-1", title: "포함" }],
    records: [],
    isCycle: false,
    timeText: (ts) => `t${ts}`,
    nodeLabel: (id) => id,
    ...extra,
  });
  const outcome = {
    result: true,
    combinator: "all" as const,
    items: [
      { path: "/output", op: "op-1", value: "PASS", actual: "…all tests PASS (12)", hasActual: true, result: true },
      { path: "/status", op: "op-gone", value: "ok", actual: "가".repeat(300), hasActual: true, result: false },
    ],
  };
  it("상태와 판정 근거 줄(아이콘+글자, 연산자 제목, 실제 값)을 그린다", () => {
    render(<EdgeJudgementView {...props({ condition: outcome })} />);
    expect(screen.getByText(/✓ 통과/)).toBeTruthy();
    expect(screen.getByText("모두 만족 → 결과: 통과")).toBeTruthy();
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByLabelText("충족")).toBeTruthy();
    expect(within(items[0]!).getByText("포함")).toBeTruthy();
    expect(within(items[1]!).getByLabelText("불충족")).toBeTruthy();
    // 연산자 목록에 없으면 id 그대로
    expect(within(items[1]!).getByText("op-gone")).toBeTruthy();
  });
  it("긴 실제 값은 180자에서 잘리고 [전체 보기]로 전문을 연다", () => {
    render(<EdgeJudgementView {...props({ condition: outcome })} />);
    const items = screen.getAllByRole("listitem");
    expect(within(items[1]!).getByText(/…”/)).toBeTruthy();
    fireEvent.click(within(items[1]!).getByRole("button", { name: "전체 보기" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("가".repeat(300));
  });
  it("해석할 수 없는 근거는 원본 JSON으로, 연산자 목록이 없어도 id로 그린다", () => {
    render(<EdgeJudgementView {...props({ condition: null, rawCondition: { weird: 1 }, operators: null })} />);
    expect(screen.getByText("판정 근거를 해석할 수 없어 원본을 보입니다")).toBeTruthy();
    expect(screen.getByText(/"weird": 1/)).toBeTruthy();
  });
  it("근거가 없으면 판정 근거 구역이 없고, 지나간 적 없으면 안내만", () => {
    const { rerender } = render(<EdgeJudgementView {...props({ condition: undefined })} />);
    expect(screen.queryByText("판정 근거")).toBeNull();
    rerender(<EdgeJudgementView {...props({ status: "none", passes: 0, statusTime: undefined })} />);
    expect(screen.getByText("아직 지나가지 않았습니다")).toBeTruthy();
    expect(screen.queryByText("지나간 기록")).toBeNull();
  });
  it("반복 연결의 기록: 회차 열, 도착 노드 n회차 시작 링크, 한도 도달 경고", () => {
    const onSee = vi.fn();
    render(
      <EdgeJudgementView
        {...props({
          isCycle: true,
          records: [
            { kind: "passed", seq: 1, ts: 100, condition: undefined },
            { kind: "iteration", seq: 2, ts: 101, iteration: 1, nodeIds: ["a"] },
            { kind: "exhausted", seq: 3, ts: 102, maxIterations: 3 },
          ],
          onSeeIteration: onSee,
          nodeLabel: (id) => `노드${id}`,
        })}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "회차" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "→ 노드a 2회차 시작" }));
    expect(onSee).toHaveBeenCalledWith("a", 1);
    expect(screen.getByText(/반복 한도에 도달했습니다 \(한도 3회\)/)).toBeTruthy();
  });
  it("로딩·오류 상태", () => {
    const retry = vi.fn();
    const { rerender } = render(<EdgeJudgementView {...props({ loading: true })} />);
    expect(screen.getByRole("status").textContent).toContain("불러오는 중");
    rerender(<EdgeJudgementView {...props({ failed: true, onRetry: retry })} />);
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(retry).toHaveBeenCalled();
  });
});
