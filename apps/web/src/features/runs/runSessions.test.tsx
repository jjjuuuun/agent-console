import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, NodeRun, RunEvent, TraceSpan } from "@agent-console/contracts";
import { IconRegistryProvider } from "@agent-console/ui";
import { appIcons } from "../../app/icons";
import { AgentsTab } from "./AgentsTab";
import { RunSessionsChip } from "./RunSessionsChip";
import { buildSessionAnnotations } from "./runSessionView";
import { EMPTY_SESSIONS, NO_SESSION, deriveRunSessions, sessionOfEvent } from "./runSessions";

afterEach(cleanup);

const label = (id: string) => `노드-${id}`;
const span = (over: Partial<TraceSpan> & { id: string }): TraceSpan => ({ kind: "k-any", ...over }) as TraceSpan;
const nodeRun = (over: Partial<NodeRun> & { node_id: string }): NodeRun => ({ status: "succeeded", ...over }) as NodeRun;
const ev = (seq: number, type: string, path: string[], actor?: string): RunEvent => ({ seq, ts: seq, type, node_path: path, ...(actor ? { actor } : {}), payload: {} }) as RunEvent;

describe("세션 계산(trace span 기준, NodeRun 폴백)", () => {
  it("span 세션 id로 세고, 시작 시각 오름차순으로 번호를 붙이며 같은 id는 같은 세션이다", () => {
    const s = deriveRunSessions({
      runId: "r",
      nodeRuns: [],
      spans: [
        span({ id: "1", node_id: "b", session_id: "sess-B", started_at: 20, ended_at: 30 }),
        span({ id: "2", node_id: "a", session_id: "sess-A", started_at: 10, ended_at: 15 }),
        span({ id: "3", node_id: "b2", session_id: "sess-B", started_at: 25 }),
        // 같은 세션 서브에이전트(parent_id)는 새 세션을 만들지 않고 세션 이름·시작을 바꾸지 않는다
        span({ id: "4", node_id: "sub", parent_id: "2", session_id: "sess-A", started_at: 11 }),
      ],
      events: [],
      labelOf: label,
    });
    expect(s.list.map((x) => [x.number, x.id, x.name])).toEqual([[1, "sess-A", "노드-a"], [2, "sess-B", "노드-b"]]);
    expect(s.byNode.get("sub")?.id).toBe("sess-A");
    expect(s.list[0]!.color).toBe("var(--ac-session-0)");
    expect(s.byId.get("sess-B")!.endedAt).toBe(30);
  });
  it("7번째 세션부터 색이 되풀이된다", () => {
    const spans = Array.from({ length: 7 }, (_, i) => span({ id: `s${i}`, node_id: `n${i}`, session_id: `x${i}`, started_at: i }));
    const s = deriveRunSessions({ runId: "r", nodeRuns: [], spans, events: [], labelOf: label });
    expect(s.list[6]!.number).toBe(7);
    expect(s.list[6]!.color).toBe("var(--ac-session-0)");
  });
  it("span이 없으면 NodeRun의 backend_session_id로 폴백하고, 세션 id가 없으면 빈 결과", () => {
    const s = deriveRunSessions({ runId: "r", nodeRuns: [nodeRun({ node_id: "n1", backend_session_id: "b1", started_at: 1 }), nodeRun({ node_id: "n2" })], spans: undefined, events: [], labelOf: label });
    expect(s.list.map((x) => x.id)).toEqual(["b1"]);
    expect(deriveRunSessions({ runId: "r", nodeRuns: [nodeRun({ node_id: "n2" })], spans: [], events: [], labelOf: label }).list).toEqual([]);
  });
  it("세션 id를 모르는 실행은 센다(툴팁용). 자식 실행 span은 세지 않는다", () => {
    const s = deriveRunSessions({
      runId: "r", nodeRuns: [],
      spans: [span({ id: "1", node_id: "a", session_id: "x", started_at: 1 }), span({ id: "2", node_id: "b" }), span({ id: "3", node_id: "c", run_id: "child", session_id: "y", started_at: 2 }), span({ id: "4", interaction_id: "i" })],
      events: [], labelOf: label,
    });
    expect(s.list.map((x) => x.id)).toEqual(["x"]);
    expect(s.unknownCount).toBe(1);
  });
  it("서브 호출 수는 위임자 노드별로 세고, 시작만 있고 멈춤이 없으면 진행 중이다", () => {
    const s = deriveRunSessions({
      runId: "r", nodeRuns: [], spans: [span({ id: "1", node_id: "L", session_id: "x", started_at: 1 })],
      events: [ev(1, "agent.subagent_started", ["L", "W"]), ev(2, "agent.subagent_stopped", ["L", "W"]), ev(3, "agent.subagent_started", ["L", "W2"])],
      labelOf: label, subStopType: "agent.subagent_stopped",
    });
    expect(s.subByDelegator).toEqual({ L: 3 - 1 });
    expect(s.subTotal).toBe(2);
    expect([...s.subRunning]).toEqual(["L"]);
    expect(s.list[0]!.subCalls).toBe(2);
    expect(sessionOfEvent(s, ev(9, "x", ["L", "W"]))?.id).toBe("x");
    expect(sessionOfEvent(s, ev(9, "x", ["Z"]))).toBeUndefined();
  });
});

const sessions = deriveRunSessions({
  runId: "r", nodeRuns: [],
  spans: [span({ id: "1", node_id: "L", session_id: "sa", started_at: 100, ended_at: 160 }), span({ id: "2", node_id: "W", session_id: "sb", started_at: 130, ended_at: 150 })],
  events: [ev(1, "agent.subagent_started", ["L", "S1"], "ag-sub"), ev(2, "x", ["W"], "ag-w"), ev(3, "x", [])],
  labelOf: label, subStopType: "agent.subagent_stopped",
});

describe("세션 칩·팝오버(R0)", () => {
  const mount = (over: Partial<React.ComponentProps<typeof RunSessionsChip>> = {}) => {
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <IconRegistryProvider icons={appIcons}>
          <RunSessionsChip sessions={sessions} selectedId={null} onSelect={onSelect} nowSec={200} {...over} />
        </IconRegistryProvider>
      </MemoryRouter>,
    );
    return { onSelect };
  };
  it("N개 칩과 · 서브 m, 팝오버 열 6개(로그 연동이 있으면 [로그 보기])", () => {
    mount({ logHref: (id) => `/l?session=${id}` });
    const chip = screen.getByRole("button", { name: /세션 2개/ });
    expect(screen.getByText(/서브 1/)).toBeTruthy();
    fireEvent.click(chip);
    const table = screen.getByRole("table", { name: "세션 목록" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent).slice(0, 6)).toEqual(["세션", "이름", "백엔드", "시작", "소요", "서브"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]!.textContent).toContain("S1");
    expect(rows[0]!.textContent).toContain("+0.0초");
    expect(rows[1]!.textContent).toContain("+30초");
    expect(within(table).getAllByRole("link", { name: "로그 보기" })[0]!.getAttribute("href")).toBe("/l?session=sa");
  });
  it("로그 연동이 없으면 [로그 보기]가 없고, 행을 누르면 선택, Esc로 해제", () => {
    const { onSelect } = mount();
    fireEvent.click(screen.getByRole("button", { name: /세션 2개/ }));
    expect(screen.queryByRole("link", { name: "로그 보기" })).toBeNull();
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    fireEvent.click(rows[1]!);
    expect(onSelect).toHaveBeenLastCalledWith("sb");
    fireEvent.keyDown(rows[1]!, { key: "Escape" });
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });
  it("세션 id를 아는 실행이 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<RunSessionsChip sessions={EMPTY_SESSIONS} selectedId={null} onSelect={() => {}} nowSec={0} />);
    expect(container.textContent).toBe("");
  });
});

describe("그래프 세션 표시(R0)", () => {
  const edgeTypes = [{ id: "z-deleg", title: "위임", invocation: { strategy: "m-1" }, scheduling: "none" }] as unknown as EdgeTypeDescriptor[];
  const strategies = [{ id: "m-1", title: "방식", session: "same", member_fields: [], max_depth: 1 }] as unknown as DelegationStrategyDescriptor[];
  const graph = { nodes: [{ id: "L", type: "t" }, { id: "W", type: "t" }, { id: "S1", type: "t" }], edges: [{ id: "e1", kind: "z-deleg", source: { node: "L", port: "o" }, target: { node: "S1", port: "i" } }] } as never;
  const base = { graph, edgeTypes, strategies, sessions, nodeLabel: label, selectedSessionId: null, calledNodes: new Set<string>(), onOpenSubs: () => {} };
  it("노드에 띠·S{n}·서브 표식, 같은 세션 대상에는 위임자 세션 안 · S{n} 칩과 호출 전 글자", () => {
    const a = buildSessionAnnotations(base);
    expect(a["L"]!.lead!.text).toBe("S1");
    expect(a["L"]!.stripColor).toBe("var(--ac-session-0)");
    expect(a["L"]!.tags![0]!.text).toBe("서브 1");
    expect(a["W"]!.lead!.text).toBe("S2");
    expect(a["S1"]!.foot!.title).toBe("노드-L 세션 안 · S1 · 대기(호출 전)");
    const called = buildSessionAnnotations({ ...base, calledNodes: new Set(["S1"]) });
    expect(called["S1"]!.foot!.title).toBe("노드-L 세션 안 · S1");
  });
  it("세션을 고르면 그 노드는 강조, 나머지는 흐리게", () => {
    const a = buildSessionAnnotations({ ...base, selectedSessionId: "sb" });
    expect(a["W"]!.emphasis).toBe("on");
    expect(a["L"]!.emphasis).toBe("dim");
  });
  it("세션 속성이 없는 방식이면 위임 대상 칩이 없다", () => {
    const a = buildSessionAnnotations({ ...base, strategies: [{ id: "m-1", title: "방식", member_fields: [], max_depth: 1 }] as never });
    expect(a["S1"]).toBeUndefined();
  });
});

describe("에이전트 탭 세션별 보기(R0)", () => {
  const events = [ev(1, "agent.subagent_started", ["L", "S1"], "ag-sub"), ev(2, "agent.text", ["W"], "ag-w"), ev(3, "run.note", [])];
  const mount = (mode: "by-actor" | "by-session", selectedId: string | null = null) => {
    const onModeChange = vi.fn();
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <IconRegistryProvider icons={appIcons}>
          <AgentsTab
            events={events} status="ready" onRetry={() => {}} actors={[]} onActorsChange={() => {}} agentName={(a) => `에이전트 ${a}`} isSubagent={() => false} startedAt={0} running={false}
            sessions={{ data: sessions, mode, onModeChange, selectedId, onSelect, formatTokens: () => "–", formatSeconds: (s) => `${s}초`, nowSec: 200 }}
          />
        </IconRegistryProvider>
      </MemoryRouter>,
    );
    return { onModeChange, onSelect };
  };
  it("세그먼트로 전환하고 세션 행·서브 행·세션 정보 없음 묶음을 보인다", () => {
    const { onModeChange, onSelect } = mount("by-session");
    expect(screen.getByRole("radiogroup", { name: "묶는 기준" })).toBeTruthy();
    const list = screen.getByRole("listbox", { name: "세션별" });
    expect(within(list).getByText("노드-L")).toBeTruthy();
    expect(within(list).getByText("에이전트 ag-sub")).toBeTruthy();
    fireEvent.click(within(list).getByText(/세션 정보 없음/));
    expect(onSelect).toHaveBeenCalledWith(NO_SESSION);
    fireEvent.click(screen.getByRole("radio", { name: "에이전트별" }));
    expect(onModeChange).toHaveBeenCalledWith("by-actor");
  });
  it("세션 행을 고르면 이벤트가 그 세션 것만 남는다", () => {
    mount("by-session", "sb");
    expect(screen.getAllByRole("listitem").some((li) => li.textContent?.includes("agent.text"))).toBe(true);
    expect(screen.queryByText("agent.subagent_started")).toBeNull();
  });
  it("세션 정보를 주지 않으면 세그먼트가 없다", () => {
    render(<AgentsTab events={events} status="ready" onRetry={() => {}} actors={[]} onActorsChange={() => {}} agentName={(a) => a} isSubagent={() => false} startedAt={0} running={false} />);
    expect(screen.queryByRole("radiogroup")).toBeNull();
  });
});
