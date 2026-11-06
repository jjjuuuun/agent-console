import { cleanup, render } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it } from "vitest";
import { DocumentEditor } from "./DocumentEditor";
import { DocumentStateChip, ToneChip } from "./ToneChip";
import { RulesSourceBadge } from "./RulesSourceBadge";

afterEach(cleanup);

/** 레이아웃 없는 DOM이라 색 대비는 tokens 쪽 대비 쌍 시험이 맡고 여기서는 구조 규칙만 본다. */
async function violations(el: Element) {
  const r = await axe.run(el, { rules: { "color-contrast": { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 120)).join(" | ")}`);
}

describe("접근성 (axe 0건)", () => {
  it("검사기 자신: 이름 없는 버튼은 잡는다", async () => {
    const { container } = render(<button type="button" aria-label="" />);
    expect((await violations(container)).join("\n")).toContain("button-name");
  });
  it("문서 편집기(정상·읽기 전용·충돌·파일 없음)", async () => {
    const doc = { id: "d", title: "문서", file: "a.md" };
    for (const props of [{}, { readOnly: true, readOnlyReason: "쓸 수 없음" }, { conflict: true }, { missing: true }]) {
      const { container, unmount } = render(<DocumentEditor document={doc} value={"# 제목\n본문"} onReload={() => undefined} {...props} />);
      expect(await violations(container), JSON.stringify(props)).toEqual([]);
      unmount();
    }
  });
  it("칩·출처 배지", async () => {
    const { container } = render(
      <div>
        <ToneChip label="칩" tone="info" />
        <DocumentStateChip state="x" />
        <RulesSourceBadge source="made-up" />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
});
