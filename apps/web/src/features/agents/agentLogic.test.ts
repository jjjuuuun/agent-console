import { describe, expect, it, vi } from "vitest";
import type { Agent, RunEvent } from "@agent-console/contracts";
import { filterAgents, groupActivity, loadAgent, saveAgent, settingsOf, withSettings } from "./agentLogic";

const dense = {
  kind: "agent", id: "a1", schema_version: 1, name: "에이", description: "", role: "역할", labels: [], attributes: {},
  backend: null, model: null, system_prompt: "지침", tools: null, disallowed_tools: null, limits: null, observe: null, resources: null,
  working_directory: null, prompt_template: null, prompt_input_template: "{source}: {value}", prompt_single_input_template: "{value}",
  prompt_input_separator: "\n\n", session: null, backend_options: null,
} as unknown as Agent;

describe("에이전트 저장 원문", () => {
  it("load는 서버가 준 원문과 ETag를 그대로 돌려주고 save는 보낸 문서를 기준 값으로 삼는다", async () => {
    const raw = { kind: "agent", id: "a1", schema_version: 1, name: "에이", role: "역할", system_prompt: "지침", model: null } as unknown as Agent;
    const rest = {
      getAgentVersioned: vi.fn(async () => ({ value: raw, version_hash: "h1" })),
      updateAgentVersioned: vi.fn(async () => ({ value: raw, version_hash: "h2" })),
    };
    const got = await loadAgent(rest as never, "a1");
    expect(got).toEqual({ value: raw, version_hash: "h1" });
    expect(got.value).not.toHaveProperty("prompt_input_template");
    expect(got.value).toHaveProperty("model", null);
    const saved = await saveAgent(rest as never, { ...got.value, name: "새" }, got.version_hash);
    expect(rest.updateAgentVersioned).toHaveBeenCalledWith("a1", expect.objectContaining({ name: "새" }), "h1");
    expect(saved).toEqual({ value: expect.objectContaining({ name: "새" }), version_hash: "h2" });
  });
});

describe("설정 필드 분리", () => {
  it("설정 폼 값만 뽑고 다시 합쳐도 식별 필드·숨긴 필드를 잃지 않는다", () => {
    const agent = { ...dense, model: "m", resources: [{ ref: "r" }] } as unknown as Agent;
    expect(Object.keys(settingsOf(agent, ["resources"]))).toContain("model");
    expect(settingsOf(agent, ["resources"])).not.toHaveProperty("resources");
    const next = withSettings(agent, { model: "n" }, ["resources"]);
    expect(next).toMatchObject({ id: "a1", name: "에이", model: "n", resources: [{ ref: "r" }] });
    expect(next).not.toHaveProperty("system_prompt");
  });
});

describe("목록·활동", () => {
  const agents = [{ id: "b", name: "비", role: "검증" }, { id: "a", name: "에이", description: "설명 문장" }] as unknown as Agent[];
  it("검색은 이름·역할·설명·id, 사용 필터는 사용 수를 모르면 숨기지 않는다", () => {
    expect(filterAgents(agents, "검증", "all", () => undefined).map((a) => a.id)).toEqual(["b"]);
    expect(filterAgents(agents, "문장", "all", () => undefined).map((a) => a.id)).toEqual(["a"]);
    expect(filterAgents(agents, "", "used", (id) => (id === "a" ? 2 : 0)).map((a) => a.id)).toEqual(["a"]);
    expect(filterAgents(agents, "", "unused", () => undefined)).toHaveLength(2);
  });

  it("활동은 실행별로 묶고 최근 순", () => {
    const ev = (run_id: string, ts: number, type: string) => ({ run_id, ts, type, event_id: `${run_id}${ts}`, seq: ts, node_path: [] }) as RunEvent;
    const groups = groupActivity([ev("r2", 30, "z"), ev("r1", 20, "y"), ev("r2", 10, "x")]);
    expect(groups.map((g) => [g.runId, g.count, g.firstTs, g.lastType])).toEqual([["r2", 2, 10, "z"], ["r1", 1, 20, "y"]]);
  });
});
