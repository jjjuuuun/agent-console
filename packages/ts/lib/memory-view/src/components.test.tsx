import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextSort, orderText, secretRejectedField } from "./format";
import { MemoryEntryMeta, type MemoryMetaDraft } from "./MemoryEntryMeta";
import { MemoryScopeTree } from "./MemoryScopeTree";
import { MemorySortMenu } from "./MemorySortMenu";
import { MemoryVersionDiff } from "./MemoryVersionDiff";
import { MemoryVersionList } from "./MemoryVersionList";
import { resolveMessages } from "./messages";
import { RetentionPreview } from "./RetentionPreview";
import { scopeLabel } from "./scopes";
import { SAMPLE_NOW, makeEntries, samplePlan, sampleKinds, sampleScopes, sampleVersions } from "./testing";

afterEach(cleanup);
const kinds = sampleKinds();
const scopes = sampleScopes();

describe("정렬·비밀 거부 보조", () => {
  it("nextSort: desc → asc → 기본", () => {
    expect(nextSort(null, "key")).toEqual({ key: "key", order: "desc" });
    expect(nextSort({ key: "key", order: "desc" }, "key")).toEqual({ key: "key", order: "asc" });
    expect(nextSort({ key: "key", order: "asc" }, "key")).toBeNull();
    expect(nextSort({ key: "key", order: "asc" }, "bytes")).toEqual({ key: "bytes", order: "desc" });
  });
  it("orderText: 모르는 정렬 값도 원문으로", () => {
    const m = resolveMessages();
    expect(orderText(null, m)).toBe("최신순");
    expect(orderText({ key: "updated_at", order: "desc" }, m)).toBe("최근 수정순");
    expect(orderText({ key: "zzz", order: "asc" }, m)).toBe("zzz 오름차순");
  });
  it("secretRejectedField: 세 값만, 나머지는 null", () => {
    expect(secretRejectedField("content")).toBe("content");
    expect(secretRejectedField("body")).toBeNull();
    expect(secretRejectedField(null)).toBeNull();
  });
  it("MemorySortMenu", () => {
    const onChange = vi.fn();
    render(<MemorySortMenu sorts={["updated_at", "created_at"]} value={{ key: "updated_at", order: "desc" }} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("만든 때"));
    expect(onChange).toHaveBeenCalledWith({ key: "created_at", order: "desc" });
    fireEvent.click(screen.getByLabelText("오름차순"));
    expect(onChange).toHaveBeenLastCalledWith({ key: "updated_at", order: "asc" });
  });
});

describe("MemoryScopeTree (수용 기준 2·3)", () => {
  it("종류 → 범위 두 층, 수 일치, 빈 id 종류는 자식 없음, 알 수 없는 종류는 맨 아래", () => {
    const onSelect = vi.fn();
    render(<MemoryScopeTree kinds={kinds} scopes={scopes} selected={null} onSelect={onSelect} />);
    const items = screen.getAllByRole("treeitem");
    expect(items[0]?.getAttribute("aria-label")).toBe("모든 범위, 항목 155개");
    const ledger = screen.getByRole("treeitem", { name: /^장부, 항목 12개/ });
    expect(ledger.getAttribute("aria-expanded")).toBeNull();
    expect(screen.getByRole("treeitem", { name: /^책상, 항목 88개/ }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("treeitem", { name: /^주간, 항목 2개/ })).toBeTruthy();
    expect(screen.getByText("쓸 수 없는 범위")).toBeTruthy();
    const last = items[items.length - 1] as HTMLElement;
    expect(last.getAttribute("aria-label")).toContain("알 수 없는 범위 종류");
    fireEvent.click(ledger);
    expect(onSelect).toHaveBeenCalledWith({ kind: "ledger", id: "" });
    fireEvent.click(screen.getByRole("treeitem", { name: /^g1, 항목 60개/ }));
    expect(onSelect).toHaveBeenLastCalledWith({ kind: "desk", id: "g1" });
  });
  it("이름 풀기: 삭제됨 칩 / 풀이기 없으면 칩 없음", () => {
    const { rerender } = render(<MemoryScopeTree kinds={kinds} scopes={scopes} selected={null} onSelect={() => undefined}
      resolvers={{ graph_id: (v) => (v === "g1" ? { status: "named", name: "개발팀" } : { status: "deleted" }) }} />);
    expect(screen.getByRole("treeitem", { name: /^개발팀, 항목 60개/ })).toBeTruthy();
    expect(screen.getByRole("treeitem", { name: /^g2, 항목 28개, 삭제됨/ })).toBeTruthy();
    rerender(<MemoryScopeTree kinds={kinds} scopes={scopes} selected={null} onSelect={() => undefined} />);
    expect(screen.queryByText("삭제됨")).toBeNull();
  });
  it("같은 종류의 범위가 전부 삭제됨이면 종류 행에만 한 번 표시", () => {
    render(<MemoryScopeTree kinds={kinds} scopes={scopes} selected={null} onSelect={() => undefined} resolvers={{ graph_id: () => ({ status: "deleted" }) }} />);
    const row = screen.getByRole("treeitem", { name: /^g1, 항목 60개/ });
    expect(row.textContent).not.toContain("삭제됨");
    expect(screen.getByRole("treeitem", { name: /^책상, 항목 88개/ }).textContent).toContain("삭제됨");
    expect(screen.getByRole("treeitem", { name: /^책상, 항목 88개, 삭제됨/ })).toBeTruthy();
  });
  it("접기·키보드·숨김 줄·메뉴", () => {
    const onShowHidden = vi.fn();
    const onNewIn = vi.fn();
    render(<MemoryScopeTree kinds={kinds} scopes={scopes} selected={{ kind: "desk", id: "g1" }} onSelect={() => undefined} hiddenCount={3} onShowHidden={onShowHidden} onNewIn={onNewIn} />);
    expect(screen.getByText("다른 프로젝트 범위 3개 숨김")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "모두 보기" }));
    expect(onShowHidden).toHaveBeenCalled();
    const desk = screen.getByRole("treeitem", { name: /^책상/ });
    fireEvent.click(desk);
    expect(screen.queryByRole("treeitem", { name: /^g1, 항목 60개/ })).toBeNull();
    fireEvent.click(desk);
    const g1 = screen.getByRole("treeitem", { name: /^g1, 항목 60개/ });
    expect(g1.getAttribute("aria-selected")).toBe("true");
    fireEvent.click(within(g1).getByRole("button", { name: "g1 범위 메뉴" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "이 범위로 새 항목" }));
    expect(onNewIn).toHaveBeenCalledWith({ kind: "desk", id: "g1" });
    expect(screen.getAllByRole("treeitem").filter((e) => e.getAttribute("tabindex") === "0")).toHaveLength(1);
  });
  it("범위가 없는 종류도 행이 있고 수는 0", () => {
    render(<MemoryScopeTree kinds={kinds} scopes={[]} selected={null} onSelect={() => undefined} />);
    expect(screen.getByRole("treeitem", { name: /^주간, 항목 0개/ })).toBeTruthy();
  });
});

describe("MemoryEntryMeta", () => {
  const entry = { ...makeEntries(1)[0]!, content: "x" };
  function Harness({ onCopy }: { onCopy?: (t: string) => void }) {
    const [draft, setDraft] = useState<MemoryMetaDraft>({ tags: ["a"], contentType: "text/markdown", pinned: false });
    return <MemoryEntryMeta entry={entry} scope={scopeLabel(entry.scope, kinds[1], {})} draft={draft} onDraftChange={setDraft} {...(onCopy ? { onCopy } : {})} contentTypeSuggestions={["text/markdown"]} />;
  }
  it("태그: Enter·쉼표로 추가, 중복 무시, ✕로 지움", () => {
    render(<Harness />);
    const input = screen.getByLabelText("태그 추가");
    fireEvent.change(input, { target: { value: "b" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(input, { target: { value: "a" } });
    fireEvent.keyDown(input, { key: "," });
    expect(screen.getAllByText(/^(a|b)$/)).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "a 태그 지우기" }));
    expect(screen.queryByText("a")).toBeNull();
  });
  it("IME 조합 중 Enter는 태그를 확정하지 않는다", () => {
    render(<Harness />);
    const input = screen.getByLabelText("태그 추가");
    fireEvent.change(input, { target: { value: "ㅎ" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(screen.queryByText("ㅎ")).toBeNull();
  });
  it("고정은 스위치(글자 병기), 해시 복사 콜백", () => {
    const onCopy = vi.fn();
    render(<Harness onCopy={onCopy} />);
    const sw = screen.getByRole("switch", { name: "고정" });
    fireEvent.click(sw);
    expect(screen.getAllByText("켜짐").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "해시 복사" }));
    expect(onCopy).toHaveBeenCalledWith(entry.sha256);
  });
});

describe("MemoryVersionList / MemoryVersionDiff (수용 기준 20)", () => {
  it("최신순, 모르는 op·kind는 원문, 크기 변화", () => {
    const onSelect = vi.fn();
    render(<MemoryVersionList versions={sampleVersions()} selected={5} onSelect={onSelect} currentVersion={5} now={SAMPLE_NOW} />);
    const rows = screen.getAllByRole("option");
    expect(rows.map((r) => r.getAttribute("data-version"))).toEqual(["5", "4", "3", "2", "1"]);
    expect(rows[0]?.textContent).toContain("future-op");
    expect(rows[0]?.textContent).toContain("r2");
    expect(rows[1]?.textContent).toContain("옮김");
    expect(rows[3]?.textContent).toContain("+40 B");
    expect(rows[4]?.textContent).not.toMatch(/[+−]\d/);
    fireEvent.keyDown(rows[0] as HTMLElement, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenCalledWith(4);
  });
  it("로딩 스켈레톤 6행, 오류는 다시 시도", () => {
    const onRetry = vi.fn();
    const { container, rerender } = render(<MemoryVersionList versions={[]} selected={null} onSelect={() => undefined} loading />);
    expect(container.querySelectorAll(".ac-mem-skeleton")).toHaveLength(6);
    rerender(<MemoryVersionList versions={[]} selected={null} onSelect={() => undefined} error onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetry).toHaveBeenCalled();
  });
  const v = sampleVersions();
  const common = { compare: "prev" as const, onCompareChange: () => undefined, layout: "split" as const, onLayoutChange: () => undefined, isCurrent: false };
  it("본문 없는 동작(보관·옮김)은 본문 변경 없음 + 바뀐 값", () => {
    const { rerender } = render(<MemoryVersionDiff {...common} version={v[3]!} base={v[2]!} />);
    expect(screen.getByText("본문 변경 없음")).toBeTruthy();
    expect(screen.getByText("키: a/b → a/c")).toBeTruthy();
    rerender(<MemoryVersionDiff {...common} version={v[2]!} base={v[1]!} />);
    expect(screen.getByText("보관: 켜짐")).toBeTruthy();
  });
  it("본문 비교는 TextDiff를 쓰고, 되돌리기는 현재 버전에서 비활성", () => {
    const onRestore = vi.fn();
    const { rerender, container } = render(<MemoryVersionDiff {...common} version={v[1]!} base={v[0]!} versionContent="b" baseContent="a" onRestore={onRestore} />);
    expect(container.querySelector(".cm-mergeView, .cm-editor")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "이 버전으로 되돌리기" }));
    expect(onRestore).toHaveBeenCalledWith(2);
    rerender(<MemoryVersionDiff {...common} version={v[1]!} base={v[0]!} versionContent="b" baseContent="a" onRestore={onRestore} isCurrent />);
    expect((screen.getByRole("button", { name: "지금 버전입니다" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("보기 전환·비교 대상 전환 콜백, 본문 로딩 중에는 스피너", () => {
    const onCompareChange = vi.fn();
    const onLayoutChange = vi.fn();
    render(<MemoryVersionDiff {...common} onCompareChange={onCompareChange} onLayoutChange={onLayoutChange} version={v[1]!} base={v[0]!} />);
    expect(screen.getByRole("status")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "비교 대상: 현재와" }));
    expect(onCompareChange).toHaveBeenCalledWith("current");
    fireEvent.click(screen.getByRole("radio", { name: "비교 보기 방식: 한 줄" }));
    expect(onLayoutChange).toHaveBeenCalledWith("unified");
  });
  it("삭제 동작은 '지움'이라고만", () => {
    render(<MemoryVersionDiff {...common} version={{ ...v[1]!, op: "delete" }} base={v[0]!} />);
    expect(screen.getAllByText("지움").length).toBeGreaterThan(0);
  });
});

describe("RetentionPreview (수용 기준 26)", () => {
  const base = { ruleCount: 1, onPreview: () => undefined, now: SAMPLE_NOW };
  it("규칙이 0개면 호출 불가 + 안내", () => {
    render(<RetentionPreview {...base} ruleCount={0} plan={null} />);
    expect(screen.getByText("규칙이 없습니다.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "미리보기" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("요약·표·행 수 상한과 '외 n개'", () => {
    const plan = { ...samplePlan(300), count: 500 };
    render(<RetentionPreview {...base} plan={plan} excludedPinned={4} detailOf={() => ({ updated_at: SAMPLE_NOW - 3 * 86_400, bytes: 400 })} />);
    expect(screen.getByText(/대상 500개 — 보관 150 · 지우기 150/)).toBeTruthy();
    expect(screen.getByText(/고정 4개 제외/)).toBeTruthy();
    expect(screen.getByText("처음 200개만 보입니다. 외 300개")).toBeTruthy();
    expect(screen.getAllByRole("row").length).toBeLessThan(40);
    expect(screen.getAllByText("3일 전").length).toBeGreaterThan(0);
  });
  it("detailOf·excludedPinned를 생략하면 계획 항목의 updated_at·bytes와 계획의 excluded_pinned를 쓴다(5.7R.28)", () => {
    const one = samplePlan(1);
    const item = { ...one.items![0]!, updated_at: SAMPLE_NOW - 2 * 86_400, bytes: 512 };
    const { unmount } = render(<RetentionPreview {...base} plan={{ ...one, items: [item], excluded_pinned: 3 }} />);
    expect(screen.getByText(/고정 3개 제외/)).toBeTruthy();
    expect(screen.getByText("2일 전")).toBeTruthy();
    expect(screen.getByText("512 B")).toBeTruthy();
    unmount();
    render(<RetentionPreview {...base} plan={{ ...one, excluded_pinned: 0 }} />);
    expect(screen.queryByText(/고정 \d+개 제외/)).toBeNull();
  });
  it("[지금 적용]은 canApply일 때만, 꺼진 이유를 보인다", () => {
    const onApply = vi.fn();
    const { rerender } = render(<RetentionPreview {...base} plan={samplePlan()} onApply={onApply} canApply={false} applyBlockedReason="먼저 저장하세요" />);
    expect((screen.getByRole("button", { name: "지금 적용" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("먼저 저장하세요")).toBeTruthy();
    rerender(<RetentionPreview {...base} plan={samplePlan()} onApply={onApply} canApply result={{ archived: 2, deleted: 1, skipped: 0 }} />);
    fireEvent.click(screen.getByRole("button", { name: "지금 적용" }));
    expect(onApply).toHaveBeenCalled();
    expect(screen.getByText(/보관 2 · 지움 1 · 건너뜀 0/)).toBeTruthy();
  });
  it("지우기 동작은 아이콘 + 글자", () => {
    render(<RetentionPreview {...base} plan={samplePlan(2)} />);
    const chips = document.querySelectorAll('.ac-mem-chip[data-tone="danger"]');
    expect(chips).toHaveLength(1);
    expect(chips[0]?.querySelector(".ac-mem-icon-failed")).toBeTruthy();
    expect(chips[0]?.textContent).toBe("지우기");
  });
  void act;
});
