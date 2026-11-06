import { cleanup, render } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { AuthorChip, OpChip } from "./Chips";
import { HistoryDiff } from "./HistoryDiff";
import { LinkGraph } from "./LinkGraph";
import { LinkList } from "./LinkList";
import { LintTable } from "./LintTable";
import { MovePageForm } from "./MovePageForm";
import { NewPageForm } from "./NewPageForm";
import { OutlinksPanel } from "./OutlinksPanel";
import { PageHistory } from "./PageHistory";
import { PageTree } from "./PageTree";
import { PageView } from "./PageView";
import { RuleListEditor } from "./RuleListEditor";
import { SearchResults } from "./SearchResults";
import { SyntaxValueTree } from "./SyntaxValueTree";
import { sampleDisplay, sampleGraph, sampleHits, sampleIssues, samplePages, samplePageView, sampleVersions, SAMPLE_NOW } from "./testing";

afterEach(cleanup);

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  if (!("DOMMatrixReadOnly" in globalThis)) {
    (globalThis as unknown as Record<string, unknown>).DOMMatrixReadOnly = class {
      m22 = 1;
      constructor(public transform?: string) {}
    };
  }
});

/** 레이아웃 없는 DOM이라 색 대비는 tokens.test(대비 쌍)가 맡고 여기서는 구조 규칙만 본다. */
async function violations(el: Element) {
  const r = await axe.run(el, { rules: { "color-contrast": { enabled: false } } });
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 120)).join(" | ")}`);
}

describe("접근성 (axe 0건)", () => {
  it("검사기 자신: 이름 없는 버튼은 잡는다", async () => {
    const { container } = render(<button type="button" aria-label="" />);
    expect((await violations(container)).join("\n")).toContain("button-name");
  });
  it("칩·트리·본문·링크 패널", async () => {
    const { container } = render(
      <div>
        <AuthorChip author={{ kind: "agent", agent_id: "a", run_id: "run-123456789" }} display={sampleDisplay()} onOpenRun={() => undefined} />
        <OpChip op="zap" display={sampleDisplay()} />
        <PageTree pages={samplePages()} selectedPath="notes/first" expanded={new Set(["notes"])} onExpandedChange={() => undefined} height={300} />
        <PageView page={samplePageView()} onOpenPage={() => undefined} />
        <OutlinksPanel content={samplePageView().content} links={samplePageView().links ?? []} height={200} onCreate={() => undefined} />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
  it("기록·비교", async () => {
    const { container } = render(
      <div>
        <PageHistory versions={sampleVersions()} now={SAMPLE_NOW} display={sampleDisplay()} onCompare={() => undefined} onRestore={() => undefined} pruned height={300} />
        <PageHistory versions={[]} unavailable />
        <HistoryDiff version={2} content="가" previousContent="나" currentContent="다" onClose={() => undefined} />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
  it("그래프·연결 목록", async () => {
    const { container } = render(
      <div>
        <LinkGraph graph={sampleGraph()} centerPath="a" engine={async () => ({})} height={300} />
        <LinkList graph={sampleGraph()} centerPath="a" height={300} />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
  it("점검 표·검색 결과", async () => {
    const { container } = render(
      <div>
        <LintTable issues={sampleIssues()} display={sampleDisplay()} severityOrder={["error", "warning", "info"]} height={300} />
        <SearchResults hits={sampleHits()} query="q" degraded />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
  it("폼 4종", async () => {
    const { container } = render(
      <div>
        <NewPageForm value={{ path: "a", title: "", templateId: "t", variables: {} }} onChange={() => undefined} templates={[{ id: "t", title: "틀", file: "f", rule_id: "r", variables: [{ name: "주제" }] }]} existingPaths={["a"]} onSubmit={() => undefined} pathError="오류" />
        <MovePageForm from="a" to="b" onToChange={() => undefined} rewriteLinks onRewriteLinksChange={() => undefined} onSubmit={() => undefined} preview={{ from: "a", to: "b", rewritten: [{ path: "c", count: 1 }], conflicts: [] }} />
        <RuleListEditor value={[{ id: "r1", name: "가" }, { id: "x", missing: true }]} onChange={() => undefined} onImport={() => undefined} onOpen={() => undefined} />
        <SyntaxValueTree syntax={{ syntax: { links: [{ id: "a", kind: "k" }] }, sources: { "/links": "default" } }} />
      </div>,
    );
    expect(await violations(container)).toEqual([]);
  });
});
