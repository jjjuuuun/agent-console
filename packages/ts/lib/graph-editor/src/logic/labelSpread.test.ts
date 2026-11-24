import { describe, expect, it } from "vitest";
import { spreadLabels, type SpreadInput } from "./labelSpread";

const line = (y: number): SpreadInput["labelAt"] => (t) => ({ x: t * 1000, y });
const same: SpreadInput["labelAt"] = (t) => ({ x: t * 1000, y: 0 });

describe("spreadLabels", () => {
  it("겹치지 않는 라벨은 건드리지 않는다", () => {
    const out = spreadLabels([{ id: "a", labelAt: line(0) }, { id: "b", labelAt: line(200) }]);
    expect(out.size).toBe(0);
  });
  it("같은 경로를 쓰는 라벨은 서로 다른 자리로 옮긴다", () => {
    const out = spreadLabels([{ id: "a", labelAt: same }, { id: "b", labelAt: same }, { id: "c", labelAt: same }]);
    const ts = ["a", "b", "c"].map((k) => out.get(k) ?? 0.5);
    expect(new Set(ts).size).toBe(3);
    expect(out.has("a")).toBe(false);
  });
  it("사용자가 위치를 정한 라벨은 그 자리를 피해서 다른 라벨이 옮긴다", () => {
    const out = spreadLabels([{ id: "pin", labelAt: same, fixed: { t: 0.5 } }, { id: "b", labelAt: same }]);
    expect(out.get("b")).not.toBe(undefined);
    expect(out.has("pin")).toBe(false);
  });
  it("보이지 않는 라벨은 자리를 차지하지 않는다", () => {
    const out = spreadLabels([{ id: "hidden", labelAt: same, visible: false }, { id: "b", labelAt: same }]);
    expect(out.size).toBe(0);
  });
  it("같은 노드에서 갈라지는 3개 이상의 라벨이 잰 크기 기준으로 서로 겹치지 않는다", () => {
    // 세 연결선이 앞 구간을 함께 쓰고 y만 조금씩 다르다(위임자 하나 -> 세 위임받는 에이전트)
    const size = { width: 150, height: 40 };
    const inputs: SpreadInput[] = [0, 1, 2].map((k) => ({ id: `e${k}`, size, labelAt: (t) => ({ x: t * 600, y: k * 10 }) }));
    const out = spreadLabels(inputs);
    const pos = inputs.map((i) => i.labelAt(out.get(i.id) ?? 0.5));
    for (let a = 0; a < pos.length; a++) {
      for (let b = a + 1; b < pos.length; b++) {
        const pa = pos[a] as { x: number; y: number };
        const pb = pos[b] as { x: number; y: number };
        const clear = Math.abs(pa.x - pb.x) >= size.width || Math.abs(pa.y - pb.y) >= size.height;
        expect(clear).toBe(true);
      }
    }
  });
  it("라벨마다 크기가 달라도 각자 크기로 겹침을 판단한다", () => {
    const out = spreadLabels([
      { id: "a", labelAt: same, size: { width: 300, height: 20 } },
      { id: "b", labelAt: same, size: { width: 20, height: 20 } },
    ]);
    const b = out.get("b") ?? 0.5;
    expect(Math.abs(b * 1000 - 500)).toBeGreaterThanOrEqual(160);
  });
  it("노드를 덮지 않는 자리가 있으면 그 자리를 고르고, 없으면 라벨끼리만 피한다", () => {
    const size = { width: 100, height: 20 };
    const wall = { x: 400, y: -50, width: 300, height: 100 };
    const out = spreadLabels([{ id: "a", labelAt: same, size }], undefined, [wall]);
    const t = out.get("a") ?? 0.5;
    const x = t * 1000;
    expect(x + 50 <= 400 || x - 50 >= 700).toBe(true);
    const everywhere = { x: -1000, y: -50, width: 4000, height: 100 };
    const out2 = spreadLabels([{ id: "a", labelAt: same, size }, { id: "b", labelAt: same, size }], undefined, [everywhere]);
    expect(out2.get("b")).not.toBe(undefined);
  });
  it("좁은 틈(같은 구간을 쓰는 3개, 노드를 완전히 피할 자리 없음)에서도 라벨끼리는 겹치지 않는다", () => {
    // 가로 구간(x 500~600, y 280)을 같이 쓰고, 세로 구간(x 594)은 오른쪽 노드(x 640~)를 20px 덮는 자리다(실화면 sdk 팀 모양)
    const size = { width: 133, height: 40 };
    const inputs: SpreadInput[] = [0, 1, 2].map((k) => ({ id: `s${k}`, size, labelAt: k === 0 ? (t) => ({ x: 594, y: 230 - (t - 0.5) * 300 }) : k === 1 ? (t) => ({ x: 560 + (t - 0.5) * 100, y: 280 }) : (t) => ({ x: 597, y: 299 + (t - 0.5) * 270 }) }));
    const out = spreadLabels(inputs, undefined, [{ x: 640, y: 0, width: 160, height: 470 }]);
    const pos = inputs.map((i) => i.labelAt(out.get(i.id) ?? 0.5));
    for (let a = 0; a < 3; a++) for (let b = a + 1; b < 3; b++) {
      const pa = pos[a] as { x: number; y: number };
      const pb = pos[b] as { x: number; y: number };
      expect(Math.abs(pa.x - pb.x) >= size.width || Math.abs(pa.y - pb.y) >= size.height).toBe(true);
    }
  });
  it("앞 라벨이 뒤 라벨의 유일한 자리를 차지하지 않는다(되짚기): 가로 한 줄만 쓰는 라벨 하나와 세로로 움직일 수 있는 라벨 둘", () => {
    const size = { width: 127, height: 40 };
    const horizontal: SpreadInput["labelAt"] = (t) => ({ x: 497 + (t - 0.14) * 146, y: 260 });
    const vertical = (y0: number): SpreadInput["labelAt"] => (t) => ({ x: 597, y: y0 + (t - 0.5) * 300 });
    const inputs: SpreadInput[] = [
      { id: "up", size, labelAt: vertical(227) },
      { id: "mid", size, labelAt: horizontal },
      { id: "down", size, labelAt: vertical(293) },
    ];
    const out = spreadLabels(inputs);
    const pos = inputs.map((i) => i.labelAt(out.get(i.id) ?? 0.5));
    for (let a = 0; a < 3; a++) for (let b = a + 1; b < 3; b++) {
      const pa = pos[a] as { x: number; y: number };
      const pb = pos[b] as { x: number; y: number };
      expect(Math.abs(pa.x - pb.x) >= size.width || Math.abs(pa.y - pb.y) >= size.height).toBe(true);
    }
  });
});
