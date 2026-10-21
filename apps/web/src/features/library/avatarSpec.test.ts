import { describe, expect, it } from "vitest";
import { categoryColorVar } from "@agent-console/graph-editor";
import { nodeAvatarsOf, readAvatarUi, resolveAvatar, resolveAvatarColor, withAvatarUi } from "./avatarSpec";

describe("resolveAvatar", () => {
  it("표시 설정이 없으면 이름 첫 글자 + id 해시 색", () => {
    expect(resolveAvatar({ id: "pl", name: "기획자" })).toEqual({ text: "기", color: categoryColorVar("pl") });
  });
  it("attributes.ui.icon·color가 우선한다(토큰·CSS 색)", () => {
    expect(resolveAvatar({ id: "a", name: "가", attributes: { ui: { icon: "🚀", color: "3" } } })).toEqual({ text: "🚀", color: "var(--ac-cat-3)" });
    expect(resolveAvatar({ id: "a", name: "가", attributes: { ui: { color: "#ff0000" } } }).color).toBe("#ff0000");
  });
  it("해석할 수 없는 값은 기본으로 돌아간다", () => {
    const r = resolveAvatar({ id: "a", name: "가", attributes: { ui: { icon: "너무길다", color: "url(x)" } } });
    expect(r).toEqual({ text: "가", color: categoryColorVar("a") });
    expect(resolveAvatarColor("cat-9")).toBeUndefined();
  });
});

describe("withAvatarUi", () => {
  it("비우면 ui 키를 지우고 다른 속성은 보존한다", () => {
    const a = withAvatarUi({ other: 1 }, { icon: "A" });
    expect(readAvatarUi(a).icon).toBe("A");
    expect(withAvatarUi(a, { icon: "" })).toEqual({ other: 1 });
    expect(withAvatarUi({ ui: { icon: "A" } }, { icon: "" })).toBeUndefined();
  });
});

describe("nodeAvatarsOf", () => {
  it("binds로 묶인 에이전트 노드만 키를 만든다", () => {
    const out = nodeAvatarsOf(
      [{ id: "n1", type: "agent", config: { agent: "x" } }, { id: "n2", type: "user" }],
      [{ id: "agent", binds: { kind: "agent", field: "agent" } }, { id: "user" }],
      [{ id: "x", name: "엑스", kind: "agent", attributes: { ui: { icon: "X" } } }],
    );
    expect(out).toEqual({ n1: { text: "X", color: categoryColorVar("x") } });
  });
});
