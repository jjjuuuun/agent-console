import { describe, expect, it } from "vitest";
import { LABEL_SPACING_DEFAULTS, flowGap, portObstacles, resolveLabelSpacing, spreadLabelLayout, spreadLabels, type ObstacleRect, type SpreadInput } from "./labelSpread";

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

describe("라벨 간격 설정(LabelSpacing)", () => {
  const size = { width: 100, height: 20 };
  const gapOf = (a: { x: number; y: number }, b: { x: number; y: number }): number => Math.max(Math.abs(a.x - b.x) - size.width, Math.abs(a.y - b.y) - size.height);
  const two: SpreadInput[] = [{ id: "a", size, labelAt: same }, { id: "b", size, labelAt: same }];
  const spaced = (zoom: number, sp = {}): number => {
    const out = spreadLabels(two, undefined, [], sp, zoom);
    return gapOf(same(out.get("a") ?? 0.5), same(out.get("b") ?? 0.5)) * Math.min(1, Math.max(0.5, zoom));
  };

  it("인자 기본값: 화면 8px, 최소 4px, 노드 봐주기 8, 포트 여백 4, 줌 0.5~1, 200ms", () => {
    expect(resolveLabelSpacing(undefined)).toEqual(LABEL_SPACING_DEFAULTS);
    expect(LABEL_SPACING_DEFAULTS).toMatchObject({ gap: 8, minGap: 4, nodeTolerance: 8, portClearance: 4, minZoom: 0.5, maxZoom: 1, settleMs: 200 });
    expect(resolveLabelSpacing({ gap: -3, minGap: 99 }).gap).toBe(8);
    expect(resolveLabelSpacing({ gap: 6, minGap: 99 }).minGap).toBe(6);
  });
  it("흐름 간격 = 화면 px ÷ 줌, 줌은 [0.5, 1]로 자른다", () => {
    const z = { minZoom: 0.5, maxZoom: 1 };
    expect(flowGap(8, 0.5, z)).toBe(16);
    expect(flowGap(8, 0.25, z)).toBe(16);
    expect(flowGap(8, 2, z)).toBe(8);
    expect(flowGap(8, 0.8, z)).toBeCloseTo(10);
  });
  it("라벨 사이 화면 간격이 줌이 달라도 목표(8px) 이상이다", () => {
    for (const zoom of [0.5, 0.6, 0.75, 1]) expect(spaced(zoom)).toBeGreaterThanOrEqual(8 - 1e-6);
  });
  it("gap 설정을 바꾸면 간격이 따라 바뀐다", () => {
    expect(spaced(1, { gap: 40 })).toBeGreaterThanOrEqual(40 - 1e-6);
  });
  it("자리가 모자라면 간격을 minGap까지 줄이되 라벨끼리 겹치지 않는다", () => {
    // 경로가 짧아 8px 간격 자리는 없고 4px 자리만 있다
    const tight: SpreadInput["labelAt"] = (t) => ({ x: t * 122, y: 0 });
    const inputs: SpreadInput[] = [{ id: "a", size, labelAt: tight }, { id: "b", size, labelAt: tight }];
    const out = spreadLabels(inputs, undefined, [], { gap: 8, minGap: 4 }, 1);
    const g = gapOf(tight(out.get("a") ?? 0.5), tight(out.get("b") ?? 0.5));
    expect(g).toBeGreaterThanOrEqual(4);
    expect(g).toBeLessThan(8);
  });
  it("포트 장애물(protect)은 노드 봐주기 단계에서도 줄이지 않는다", () => {
    const wall: ObstacleRect = { x: 400, y: -50, width: 300, height: 100 };
    const port: ObstacleRect = { x: 450, y: -10, width: 20, height: 20, protect: true };
    // 노드 안으로 8px 들어가도 되지만 포트(x 450~470)는 덮지 않아야 한다
    const out = spreadLabels([{ id: "a", labelAt: same, size }], undefined, [wall, port], { nodeTolerance: 8 }, 1);
    const x = (out.get("a") ?? 0.5) * 1000;
    expect(x + 50 <= 450 || x - 50 >= 470).toBe(true);
  });
  it("노드 본문은 기본 0, 모자랄 때만 nodeTolerance까지 덮는다", () => {
    const wall: ObstacleRect = { x: 480, y: -50, width: 40, height: 100 };
    // 경로가 x 400~600 안이라 벽(480~520)을 완전히 피하는 자리가 있다 -> 덮지 않는다
    const free: SpreadInput["labelAt"] = (t) => ({ x: 400 + t * 200, y: 0 });
    const out = spreadLabels([{ id: "a", labelAt: free, size }], undefined, [wall], undefined, 1);
    const x = 400 + (out.get("a") ?? 0.5) * 200;
    expect(x + 50 <= 480 || x - 50 >= 520).toBe(true);
  });
  it("포트 원 + 여백이 장애물이 된다(portObstacles)", () => {
    const [r] = portObstacles([{ x: 100, y: 50, ports: [{ id: "in", x: -6, y: 10, width: 10, height: 10 }, { id: "edge:l", x: 0, y: 0, width: 8, height: 90 }] }], 4, (p) => p.id === "edge:l");
    expect(portObstacles([{ x: 100, y: 50, ports: [{ x: -6, y: 10, width: 10, height: 10 }] }], 4)).toEqual([r]);
    expect(r).toEqual({ x: 90, y: 56, width: 18, height: 18, protect: true });
  });
  it("옛 호출(설정 없음)은 이전과 같다: 흐름 6px 간격", () => {
    const out = spreadLabels(two);
    expect(gapOf(same(out.get("a") ?? 0.5), same(out.get("b") ?? 0.5))).toBeGreaterThanOrEqual(6);
  });
});

describe("양보 마지막 단계", () => {
  const size = { width: 100, height: 20 };
  it("노드 봐주기로도 자리가 없으면 노드 본문을 더 덮더라도 포트는 지킨다", () => {
    // 경로 전체(x 0~1000)가 노드 안이고, 포트(x 450~470)만 따로 지키는 자리다
    const wall: ObstacleRect = { x: -100, y: -50, width: 1300, height: 100 };
    const port: ObstacleRect = { x: 450, y: -10, width: 20, height: 20, protect: true };
    const out = spreadLabels([{ id: "a", labelAt: same, size }], undefined, [wall, port], { nodeTolerance: 8 }, 1);
    const x = (out.get("a") ?? 0.5) * 1000;
    expect(x + 50 <= 450 || x - 50 >= 470).toBe(true);
  });
});

describe("칩 접기(양보 ③)", () => {
  const size = { width: 160, height: 20 };
  // 왼쪽 노드는 x 440까지, 오른쪽 노드는 560부터: 사이 120px에 폭 160 라벨은 봐주기(8px씩)로도 안 들어간다
  const walls: ObstacleRect[] = [{ x: -1000, y: -50, width: 1440, height: 100 }, { x: 560, y: -50, width: 1440, height: 100 }];
  const input = (extra: Partial<SpreadInput> = {}): SpreadInput => ({ id: "a", labelAt: same, size, ...extra });

  it("노드 봐주기로 안 되면 접어서 노드 사이에 둔다(본문 깊이 0)", () => {
    const { positions, folded } = spreadLabelLayout([input({ foldable: true })], undefined, walls, {}, 1);
    expect(folded.has("a")).toBe(true);
    const x = (positions.get("a") ?? 0.5) * 1000;
    expect(x - 22 >= 440 && x + 22 <= 560).toBe(true);
  });
  it("접을 수 없는 라벨은 접지 않는다(본문을 더 덮는 옛 양보)", () => {
    const { folded } = spreadLabelLayout([input()], undefined, walls, {}, 1);
    expect(folded.size).toBe(0);
  });
  it("접은 크기를 재어 줬으면 그 크기로 판단한다(너무 크면 접어도 안 들어간다)", () => {
    const { folded } = spreadLabelLayout([input({ foldable: true, foldedSize: { width: 140, height: 20 } })], undefined, walls, {}, 1);
    expect(folded.size).toBe(0);
  });
  it("fold: false면 접지 않는다", () => {
    expect(spreadLabelLayout([input({ foldable: true })], undefined, walls, { fold: false }, 1).folded.size).toBe(0);
  });
  it("자리가 있으면 접지 않는다", () => {
    expect(spreadLabelLayout([input({ foldable: true })], undefined, [], {}, 1).folded.size).toBe(0);
  });
  it("사용자가 위치를 정한 라벨은 접지 않는다", () => {
    expect(spreadLabelLayout([input({ foldable: true, fixed: { t: 0.5 } })], undefined, walls, {}, 1).folded.size).toBe(0);
  });
  it("접기가 필요한 라벨만 접는다: 안 들어가는 둘 중 앞 라벨은 그대로 둔다", () => {
    const free: SpreadInput = { id: "f", labelAt: (t) => ({ x: 2000 + t * 10, y: 500 }), size, foldable: true };
    expect(spreadLabelLayout([free, input({ foldable: true })], undefined, walls, {}, 1).folded.has("f")).toBe(false);
  });
  it("기본값에 fold(true)·접은 크기가 있다", () => {
    expect(LABEL_SPACING_DEFAULTS).toMatchObject({ fold: true, foldedWidth: 44, foldedHeight: 26 });
  });
});
