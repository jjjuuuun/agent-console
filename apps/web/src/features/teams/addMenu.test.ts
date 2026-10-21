import { describe, expect, it } from "vitest";
import type { NodeTypeDescriptor } from "@agent-console/contracts";
import { buildAddMenu } from "./addMenu";

const types = [
  { id: "x-actor", version: 1, title: "행위자", executable: true, binds: { kind: "k-agent", field: "ref" } },
  { id: "x-asset", version: 1, title: "자산", executable: false, binds: { kind: "k-res", field: "ref" } },
  { id: "x-human", version: 1, title: "사람", executable: true },
  { id: "x-hidden", version: 1, title: "숨김", executable: true, ui_hints: { hidden: true } },
  { id: "x-old", version: 1, title: "옛 타입", executable: true },
  { id: "x-old", version: 2, title: "새 타입", executable: true },
] as unknown as NodeTypeDescriptor[];

const labels = { pick: (t: string) => `${t} 고르기…`, create: (t: string) => `새 ${t}…`, node: (t: string) => `${t} 추가` };

describe("buildAddMenu: 항목은 디스크립터와 켜진 기능에서 나온다", () => {
  it("정의 종류마다 고르기·새로 만들기, 묶이지 않은 타입은 추가 항목(숨김·옛 버전은 뺀다)", () => {
    const entries = buildAddMenu({ nodeTypes: types, canPick: () => true, canCreate: () => true, labels });
    expect(entries.map((e) => e.label)).toEqual(["행위자 고르기…", "새 행위자…", "자산 고르기…", "새 자산…", "사람 추가", "새 타입 추가"]);
    expect(entries[0]!.action).toEqual({ op: "pick", kind: "k-agent" });
    expect(entries[5]!.action).toEqual({ op: "node", typeId: "x-old" });
  });

  it("정의 모듈이 꺼지면 그 종류 항목이 사라지고 노드 타입 항목만 남는다", () => {
    const entries = buildAddMenu({ nodeTypes: types, canPick: () => false, canCreate: () => false, labels });
    expect(entries.map((e) => e.id)).toEqual(["node:x-human", "node:x-old"]);
  });

  it("만들기 폼이 없는 종류는 고르기만 보인다", () => {
    const entries = buildAddMenu({ nodeTypes: types, canPick: () => true, canCreate: (k) => k === "k-agent", labels });
    expect(entries.filter((e) => e.action.op === "create").map((e) => e.id)).toEqual(["create:k-agent"]);
  });
});
