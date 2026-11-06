import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { Agent, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { RunSessionsChip } from "./RunSessionsChip";
import { deriveRunSessions } from "./runSessions";
import { sessionBackendIds } from "./sessionBackends";

afterEach(cleanup);

const types = [{ id: "t-any", binds: { field: "agent", kind: "k" } }] as unknown as NodeTypeDescriptor[];
const agents = [{ id: "ag1", kind: "k", backend: "be-x" }, { id: "ag2", kind: "k" }] as unknown as Agent[];
const graph = { nodes: [{ id: "n1", type: "t-any", config: { agent: "ag1" } }, { id: "n2", type: "t-any", config: { agent: "ag2" } }, { id: "n3", type: "t-other" }], edges: [], settings: {} } as unknown as Graph;
const sessions = deriveRunSessions({
  runId: "r",
  nodeRuns: [],
  spans: ["n1", "n2", "n3"].map((n, i) => ({ id: n, kind: "k", node_id: n, session_id: `s-${n}`, started_at: i })) as never,
  events: [],
  labelOf: (n) => n,
});

describe("세션 백엔드 열", () => {
  it("유효 백엔드 선택 규칙으로 구하고, 정의에 묶이지 않은 노드는 비운다", () => {
    const m = sessionBackendIds({ sessions, graph, nodeTypes: types, agents, defaultBackend: "be-default" });
    expect(m.get("s-n1")).toBe("be-x");
    expect(m.get("s-n2")).toBe("be-default");
    expect(m.has("s-n3")).toBe(false);
  });
  it("backendOf가 없으면 `–`, 있으면 mono 값이 나온다", () => {
    const { rerender } = render(
      <MemoryRouter>
        <RunSessionsChip sessions={sessions} selectedId={null} onSelect={() => {}} nowSec={10} />
      </MemoryRouter>,
    );
    screen.getByRole("button").click();
    expect(screen.queryByText("be-x")).toBeNull();
    rerender(
      <MemoryRouter>
        <RunSessionsChip sessions={sessions} selectedId={null} onSelect={() => {}} nowSec={10} backendOf={(id) => (id === "s-n1" ? "be-x" : undefined)} />
      </MemoryRouter>,
    );
    expect(screen.getByText("be-x")).toBeTruthy();
  });
});
