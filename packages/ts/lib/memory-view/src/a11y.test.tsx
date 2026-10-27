import { cleanup, render } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryEntryEditor } from "./MemoryEntryEditor";
import { MemoryEntryMeta } from "./MemoryEntryMeta";
import { MemoryEntryTable } from "./MemoryEntryTable";
import { MemoryScopeTree } from "./MemoryScopeTree";
import { MemorySortMenu } from "./MemorySortMenu";
import { MemoryVersionDiff } from "./MemoryVersionDiff";
import { MemoryVersionList } from "./MemoryVersionList";
import { RetentionPreview } from "./RetentionPreview";
import { scopeLabel } from "./scopes";
import { SAMPLE_NOW, makeEntries, sampleKinds, samplePlan, sampleScopes, sampleVersions } from "./testing";

afterEach(cleanup);

/** 레이아웃 없는 DOM이라 색 대비는 tokens.test(대비 쌍)가 맡고 여기서는 구조 규칙만 본다. */
async function violations(el: Element) {
  const r = await axe.run(el, { rules: { "color-contrast": { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 120)).join(" | ")}`);
}

describe("접근성 (axe 0건, 수용 기준 34)", () => {
  it("검사기 자신: 이름 없는 버튼은 잡는다", async () => {
    const { container } = render(<button type="button" aria-label="" />);
    expect((await violations(container)).join("\n")).toContain("button-name");
  });
  it("범위 나무(메뉴 포함)", async () => {
    const { container } = render(<MemoryScopeTree kinds={sampleKinds()} scopes={sampleScopes()} selected={{ kind: "desk", id: "g1" }} onSelect={() => undefined} hiddenCount={2} onShowHidden={() => undefined} onNewIn={() => undefined} onClearScope={() => undefined} />);
    expect(await violations(container)).toEqual([]);
  });
  it("항목 표(검색 중·정렬 단추)", async () => {
    const entries = [...makeEntries(3), ...makeEntries(1, { id: "arc", archived: true, pinned: false }), ...makeEntries(1, { id: "del", deleted_at: 1, pinned: false })];
    const { container } = render(<MemoryEntryTable entries={entries} width={900} now={SAMPLE_NOW} query="a" sortKeys={{ key: "key" }} sort={{ key: "key", order: "asc" }} onSortChange={() => undefined} />);
    expect(await violations(container)).toEqual([]);
  });
  it("편집기·정보", async () => {
    const entry = { ...makeEntries(1)[0]!, content: "x" };
    const { container } = render(
      <div>
        <MemoryEntryEditor value="가나다" onChange={() => undefined} entryKey="a/b" onSave={() => undefined} maxBytes={4} />
        <MemoryEntryMeta entry={entry} scope={scopeLabel(entry.scope, sampleKinds()[1], {})} draft={{ tags: ["a"], contentType: "text/markdown", pinned: true }} onDraftChange={() => undefined} onArchivedChange={() => undefined} onCopy={() => undefined} onOpenRun={() => undefined} onOpenHistory={() => undefined} />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
  it("기록·정리 미리보기·정렬 메뉴", async () => {
    const v = sampleVersions();
    const { container } = render(
      <div>
        <MemoryVersionList versions={v} selected={2} onSelect={() => undefined} now={SAMPLE_NOW} />
        <MemoryVersionDiff version={v[1]!} base={v[0]!} versionContent="b" baseContent="a" compare="prev" onCompareChange={() => undefined} layout="split" onLayoutChange={() => undefined} isCurrent={false} onRestore={() => undefined} maxVersions={50} />
        <RetentionPreview plan={samplePlan()} ruleCount={1} onPreview={() => undefined} onApply={() => undefined} now={SAMPLE_NOW} />
        <MemorySortMenu sorts={["updated_at", "key"]} value={{ key: "key", order: "asc" }} onChange={() => undefined} />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
});
