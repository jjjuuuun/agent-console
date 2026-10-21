import { describe, expect, it } from "vitest";
import { requesterName } from "./requester";

describe("requesterName: 에이전트 이름 -> node_label -> 그래프 이름 -> 노드 id", () => {
  const base = { node_id: "n-1" };
  it("에이전트 이름이 먼저", () => {
    expect(requesterName({ ...base, node_label: "라벨" }, "에이전트", "그래프")).toBe("에이전트");
  });
  it("에이전트가 없으면 서버가 준 node_label", () => {
    expect(requesterName({ ...base, node_label: "검토 지점" }, undefined, "그래프")).toBe("검토 지점");
  });
  it("node_label이 노드 id와 같으면 라벨이 없다는 뜻이라 그래프 이름을 쓴다", () => {
    expect(requesterName({ ...base, node_label: "n-1" }, undefined, "그래프")).toBe("그래프");
    expect(requesterName({ ...base }, undefined, "그래프")).toBe("그래프");
  });
  it("아무것도 없으면 노드 id(마지막 수단)", () => {
    expect(requesterName({ ...base, node_label: null }, undefined)).toBe("n-1");
  });
});
