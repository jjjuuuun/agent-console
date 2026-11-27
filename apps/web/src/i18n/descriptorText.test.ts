import { describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, NodeTypeDescriptor } from "@agent-console/contracts";
import { localizeEdgeType, localizeNodeType, localizePortSpec } from "./descriptorText";

const tr = (text: string) => ({ 사용자: "User", 받는: "In", 나: "Me", 입구: "Entry", 연결: "Message" })[text] ?? text;

describe("descriptorText", () => {
  it("노드 타입의 제목·포트 라벨·배지·아이콘을 옮기고 아이디는 그대로 둔다", () => {
    const d = { id: "user", title: "사용자", category: "사용자", static_ports: { inputs: [{ name: "hears", label: "받는" }] }, ui_hints: { badge: "입구", icon: "나", color: "blue" } } as unknown as NodeTypeDescriptor;
    const out = localizeNodeType(d, tr);
    expect(out.title).toBe("User");
    // 카테고리는 그룹 키·분류색 기준이라 옮기지 않는다(표시는 편집기 `categoryLabel`)
    expect(out.category).toBe("사용자");
    expect(out.static_ports?.inputs?.[0]).toEqual({ name: "hears", label: "In" });
    expect(out.ui_hints).toEqual({ badge: "Entry", icon: "Me", color: "blue" });
  });
  it("모르는 글자는 그대로", () => {
    expect(localizePortSpec({ outputs: [{ name: "x", label: "기타" }] }, tr).outputs?.[0]?.label).toBe("기타");
    expect(localizeEdgeType({ id: "m", title: "연결" } as EdgeTypeDescriptor, tr).title).toBe("Message");
  });
});

describe("선언형 배지·칩 라벨", () => {
  it("ui_hints.badges·chips의 label을 옮긴다", () => {
    const d = { id: "a", title: "x", ui_hints: { badges: [{ label_key: "k", label: "입구" }], chips: [{ value_pointer: "/p" }] } } as unknown as NodeTypeDescriptor;
    const out = localizeNodeType(d, tr);
    expect(out.ui_hints?.["badges"]).toEqual([{ label_key: "k", label: "Entry" }]);
    expect(out.ui_hints?.["chips"]).toEqual([{ value_pointer: "/p" }]);
  });
});
