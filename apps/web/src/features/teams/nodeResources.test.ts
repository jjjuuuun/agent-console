import { describe, expect, it } from "vitest";
import type { Graph, ResourceAttachment } from "@agent-console/contracts";
import type { ResourceLink } from "./teamsLogic";
import { diffNodeLayer, nodeLayerAttachments, ownAttachments, reorderLinkEdges, withLinkMode, withNodeOwnAttachments } from "./nodeResources";

const link = (edgeId: string, ref: string, mode = "add"): ResourceLink => ({ edge: { id: edgeId } as never, resourceNode: {} as never, resourceId: ref, mode });
const att = (ref: string, mode = "add") => ({ ref, mode }) as ResourceAttachment;

describe("노드 층 첨부 편집을 그래프 동작으로 푼다", () => {
  const links = [link("e1", "a"), link("e2", "b", "replace")];
  const own = [att("c"), att("d")];
  const old = nodeLayerAttachments(links, own);

  it("연결 + 노드 설정 첨부를 한 목록으로", () => {
    expect(old.map((a) => a.ref)).toEqual(["a", "b", "c", "d"]);
    expect(old[1]!.mode).toBe("replace");
  });

  it("추가는 마지막 항목", () => {
    expect(diffNodeLayer(old, [...old, att("z")], links)).toEqual({ kind: "add", attachment: att("z") });
  });

  it("삭제는 처음 달라지는 자리: 연결이면 연결 삭제, 아니면 설정 첨부 삭제", () => {
    expect(diffNodeLayer(old, [old[0]!, old[2]!, old[3]!], links)).toEqual({ kind: "remove-link", edgeId: "e2" });
    expect(diffNodeLayer(old, [old[0]!, old[1]!, old[3]!], links)).toEqual({ kind: "remove-own", index: 0 });
  });

  it("방식 바꾸기", () => {
    expect(diffNodeLayer(old, [old[0]!, att("b", "remove"), old[2]!, old[3]!], links)).toEqual({ kind: "mode-link", edgeId: "e2", mode: "remove" });
    expect(diffNodeLayer(old, [old[0]!, old[1]!, old[2]!, att("d", "replace")], links)).toEqual({ kind: "mode-own", index: 1, mode: "replace" });
  });

  it("순서 바꾸기는 묶음 안에서만", () => {
    expect(diffNodeLayer(old, [old[1]!, old[0]!, old[2]!, old[3]!], links)).toEqual({ kind: "reorder-links", edgeIds: ["e2", "e1"] });
    expect(diffNodeLayer(old, [old[0]!, old[1]!, old[3]!, old[2]!], links)).toEqual({ kind: "reorder-own", order: [1, 0] });
    expect(diffNodeLayer(old, [old[2]!, old[1]!, old[0]!, old[3]!], links)).toEqual({ kind: "none" });
  });
});

describe("그래프·노드 갱신", () => {
  const g = { id: "g", name: "n", nodes: [{ id: "n1", type: "t", config: { settings: { resources: [{ ref: "c" }] } } }], edges: [{ id: "e1", source: { node: "r", port: "p" }, target: { node: "n1", port: "q" }, kind: "k" }, { id: "e2", source: { node: "r2", port: "p" }, target: { node: "n1", port: "q" }, kind: "k", config: { mode: "replace" } }] } as unknown as Graph;
  it("연결 방식: 기본이면 키 삭제", () => {
    expect(withLinkMode(g, "e1", "replace", "add").edges![0]!.config).toEqual({ mode: "replace" });
    expect(withLinkMode(g, "e2", "add", "add").edges![1]).not.toHaveProperty("config");
  });
  it("연결 순서 재배치", () => {
    expect(reorderLinkEdges(g, ["e2", "e1"]).edges!.map((e) => e.id)).toEqual(["e2", "e1"]);
  });
  it("노드 설정 첨부: 비우면 settings와 config까지 정리", () => {
    const n = g.nodes![0]!;
    expect(ownAttachments(n)).toEqual([{ ref: "c" }]);
    const cleared = withNodeOwnAttachments(n, []);
    expect(cleared).not.toHaveProperty("config");
    expect(withNodeOwnAttachments(cleared, [att("x")]).config).toEqual({ settings: { resources: [att("x")] } });
  });
});
