import * as markdownDoc from "@agent-console/markdown-doc";
import { describe, expect, it } from "vitest";
import * as sdd from "./index";
import { codeDisplay, statusTone, taskTitle, toneAttr } from "./display";
import { applyPositions, createElkPlanLayout, planBundles, planToFlow } from "./plan";
import { flattenTaskRows, groupByStage, progressRatio } from "./stages";
import { manyTasks, samplePlan, sampleStages, sampleStatuses, sampleTasks } from "./testing";
import { filterTraceRows, gapLabelKey, hasGaps, verificationLabelKey } from "./trace";
import { formatMessage, messageOr, resolveMessages } from "./messages";

const isDone = (s: string) => s === "s-done";

describe("display", () => {
  it("statusTone: 정의의 라벨·톤을 쓴다", () => {
    expect(statusTone("s-doing", sampleStatuses())).toEqual({ id: "s-doing", label: "진행", tone: "info", done: false });
  });
  it("모르는 상태는 id 원문 + 중립", () => {
    expect(statusTone("zzz", sampleStatuses())).toEqual({ id: "zzz", label: "zzz", tone: "neutral", done: false });
    expect(statusTone("zzz")).toMatchObject({ label: "zzz", tone: "neutral" });
  });
  it("톤이 없고 끝난 상태는 success, 라벨이 비면 id", () => {
    expect(statusTone("a", [{ id: "a", done: true }])).toEqual({ id: "a", label: "a", tone: "success", done: true });
    expect(statusTone("a", [{ id: "a", label: "", tone: null }]).label).toBe("a");
  });
  it("toneAttr: 이상한 값은 중립", () => {
    expect(toneAttr("danger")).toBe("danger");
    expect(toneAttr("Bad Tone")).toBe("neutral");
    expect(toneAttr(null)).toBe("neutral");
    expect(toneAttr("custom-tone")).toBe("custom-tone");
  });
  it("codeDisplay: 표 → 문구 → 원문 순", () => {
    expect(codeDisplay("x", { x: { tone: "danger", label: "엑스", hint: "h" } })).toEqual({ label: "엑스", tone: "danger", hint: "h" });
    expect(codeDisplay("y", undefined, "warning", "와이")).toEqual({ label: "와이", tone: "warning" });
    expect(codeDisplay("z", {})).toEqual({ label: "z", tone: "neutral" });
  });
  it("taskTitle: 제목 → id → 키", () => {
    expect(taskTitle({ key: "k", id: "i", title: "t" })).toBe("t");
    expect(taskTitle({ key: "k", id: "i" })).toBe("i");
    expect(taskTitle({ key: "k" })).toBe("k");
  });
});

describe("stages", () => {
  it("groupByStage: 단계 순서·끝난 수·단계 없음 묶음", () => {
    const g = groupByStage(sampleTasks(), isDone);
    expect(g.map((x) => [x.key, x.done, x.total])).toEqual([["st1", 1, 2], ["st2", 0, 2], ["", 0, 1]]);
    expect(g[2]?.stage).toBeNull();
  });
  it("문서 단계 목록이 순서를 정하고 빈 단계도 남긴다", () => {
    const g = groupByStage(sampleTasks().filter((t) => t.stage?.id !== "st1"), isDone, sampleStages());
    expect(g.map((x) => [x.key, x.total])).toEqual([["st1", 0], ["st2", 2], ["", 1]]);
  });
  it("빈 입력", () => {
    expect(groupByStage([])).toEqual([]);
  });
  it("flattenTaskRows: 접힌 단계는 작업 줄을 뺀다, 단계 없음 하나면 머리도 뺀다", () => {
    const g = groupByStage(sampleTasks(), isDone);
    expect(flattenTaskRows(g).map((r) => r.key)).toEqual(["stage:st1", "task:T1", "task:T2", "stage:st2", "task:T3", "task:T4", "stage:", "task:T5"]);
    expect(flattenTaskRows(g, new Set(["st1"])).map((r) => r.key).slice(0, 3)).toEqual(["stage:st1", "stage:st2", "task:T3"]);
    expect(flattenTaskRows(groupByStage(manyTasks(2))).map((r) => r.type)).toEqual(["task", "task"]);
  });
  it("progressRatio", () => {
    expect(progressRatio(1, 4)).toBe(0.25);
    expect(progressRatio(0, 0)).toBe(0);
    expect(progressRatio(9, 4)).toBe(1);
  });
});

describe("plan", () => {
  it("planToFlow: 층별 좌표·병목·준비·막힘, 연결은 의존에서", () => {
    const f = planToFlow(samplePlan(), sampleTasks());
    const n = new Map(f.nodes.map((x) => [x.id, x] as const));
    expect(n.get("T1")?.data).toMatchObject({ layer: 0, critical: true });
    expect(n.get("T2")?.data).toMatchObject({ layer: 1, ready: true, critical: true });
    expect(n.get("T4")?.data).toMatchObject({ layer: 2, blocked: true, critical: false });
    expect(n.get("T3")?.position.x).toBeGreaterThan(n.get("T2")?.position.x ?? 0);
    expect(f.edges.map((e) => [e.id, e.critical])).toEqual([["T1->T2", true], ["T2->T3", true], ["T2->T4", false]]);
    expect(f.truncated).toBe(false);
  });
  it("층에 없는 작업은 맨 뒤 묶음, 순환 표시", () => {
    const tasks = sampleTasks();
    const f = planToFlow({ layers: [["T1"]], cycles: [["T2", "T3"]] }, tasks);
    expect(f.nodes.find((x) => x.id === "T2")?.data).toMatchObject({ layer: 1, cycle: true });
  });
  it("없는 작업을 가리키는 연결·자기 연결은 뺀다", () => {
    const f = planToFlow({ layers: [["A"]] }, [{ key: "A", status: "x", document: "d", line: 1, line_hash: "h", dependencies: ["A", "ghost"] }]);
    expect(f.edges).toEqual([]);
  });
  it("maxNodes 초과는 자르고 표시한다", () => {
    const f = planToFlow({ layers: [manyTasks(10).map((t) => t.key)] }, manyTasks(10), { maxNodes: 4 });
    expect(f.nodes).toHaveLength(4);
    expect(f.truncated).toBe(true);
  });
  it("applyPositions: 있는 것만 바꾼다", () => {
    const f = planToFlow(samplePlan(), sampleTasks());
    const g = applyPositions(f, { T1: { x: 5, y: 6 } });
    expect(g.nodes.find((x) => x.id === "T1")?.position).toEqual({ x: 5, y: 6 });
    expect(g.nodes.find((x) => x.id === "T2")?.position).toEqual(f.nodes.find((x) => x.id === "T2")?.position);
  });
  it("planBundles: 묶음 글", () => {
    const b = planBundles(samplePlan(), sampleTasks());
    expect(b.map((x) => [x.index, x.keys])).toEqual([[1, ["T1", "T5"]], [2, ["T2"]], [3, ["T3", "T4"]]]);
    expect(b[0]?.titles[0]).toBe("작업 T1");
  });
  it("createElkPlanLayout: 주입한 ELK에 그래프를 주고 좌표를 돌려받는다", async () => {
    let seen: { layoutOptions?: Record<string, string>; children?: unknown[]; edges?: unknown[] } = {};
    const engine = createElkPlanLayout(async () => ({
      layout: async (g) => {
        seen = g as typeof seen;
        return { children: [{ id: "a", x: 1, y: 2 }, { id: "b" }] };
      },
    }));
    const out = await engine({ nodes: [{ id: "a", width: 1, height: 1 }, { id: "b", width: 1, height: 1 }], edges: [{ id: "e", source: "a", target: "b" }], layerGap: 64, nodeGap: 12 });
    expect(out).toEqual({ a: { x: 1, y: 2 }, b: { x: 0, y: 0 } });
    expect(seen.layoutOptions?.["elk.direction"]).toBe("RIGHT");
    expect(seen.layoutOptions?.["elk.layered.spacing.nodeNodeBetweenLayers"]).toBe("64");
    expect(seen.edges).toHaveLength(1);
  });
  it("createElkPlanLayout: 실제 elkjs로 의존 순서대로 왼쪽→오른쪽", async () => {
    const f = planToFlow(samplePlan(), sampleTasks());
    const out = await createElkPlanLayout()({
      nodes: f.nodes.map((n) => ({ id: n.id, width: n.width, height: n.height })),
      edges: f.edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
      layerGap: 64,
      nodeGap: 12,
    });
    expect(out.T1?.x).toBeLessThan(out.T2?.x ?? -1);
    expect(out.T2?.x).toBeLessThan(out.T3?.x ?? -1);
  });
});

describe("trace·messages", () => {
  it("문구 키와 거르기", () => {
    expect(gapLabelKey("no_x")).toBe("gap.no_x");
    expect(verificationLabelKey("v")).toBe("verification.v");
    const rows = [{ id: "a", document: "d", line: 1, gaps: [] }, { id: "b", document: "d", line: 2, gaps: ["g"] }];
    expect(hasGaps(rows[1] as never)).toBe(true);
    expect(filterTraceRows(rows, true).map((r) => r.id)).toEqual(["b"]);
    expect(filterTraceRows(rows, false)).toHaveLength(2);
  });
  it("formatMessage·resolveMessages·messageOr", () => {
    expect(formatMessage("{a}/{b}", { a: 1 })).toBe("1/{b}");
    expect(resolveMessages({ "tasks.ready": "OK" })["tasks.ready"]).toBe("OK");
    expect(resolveMessages()["tasks.ready"]).toBe("준비됨");
    expect(messageOr({ a: "x" }, "b", "원문")).toBe("원문");
  });
});

describe("markdown-doc 다시 내보내기(7R.6)", () => {
  it("같은 이름이 같은 구현이다(두 벌이 아니다)", () => {
    expect(sdd.DocumentEditor).toBe(markdownDoc.DocumentEditor);
    expect(sdd.ToneChip).toBe(markdownDoc.ToneChip);
    expect(sdd.DocumentStateChip).toBe(markdownDoc.DocumentStateChip);
    expect(sdd.RulesSourceBadge).toBe(markdownDoc.RulesSourceBadge);
    expect(sdd.EDITOR_VIEW_MODES).toBe(markdownDoc.EDITOR_VIEW_MODES);
    expect(sdd.statusTone).toBe(markdownDoc.statusTone);
  });
});
