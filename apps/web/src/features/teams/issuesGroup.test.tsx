import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Graph, Issue } from "@agent-console/contracts";
import { IssuesPanel } from "./IssuesPanel";
import { previewIssues } from "./ValidationChip";
import { ignoredFieldReasons, IgnoredValueClear } from "./ignoredFields";

afterEach(cleanup);

const graph = { id: "g", name: "g", nodes: [{ id: "a", type: "t", label: "구현자" }, { id: "b", type: "t", label: "검토자" }, { id: "c", type: "t", label: "기록자" }], edges: [] } as unknown as Graph;
const unset = (n: string) => ({ id: "unset", label: "값 비우기", patch: { unset_node_fields: [{ node_id: n, path: "/settings/x" }] } });
const infos: Issue[] = ["a", "b", "c"].map(
  (n) => ({ severity: "info", code: "any.code", message: `${n} 무시됨`, node_id: n, path: "/settings/x", hint: "비워도 결과는 같습니다.", group: { key: "k", message: "이 값은 쓰이지 않습니다" }, suggestions: [unset(n)] }) as unknown as Issue,
);

function setup(issues: Issue[], extra: Partial<React.ComponentProps<typeof IssuesPanel>> = {}) {
  const apply = vi.fn();
  const openNode = vi.fn();
  render(
    <MemoryRouter>
      <IssuesPanel graph={graph} validation={{ phase: "idle", issues, validated: true }} open onToggle={() => undefined} onValidate={() => undefined} onFocus={() => undefined} onApplySuggestion={apply} onOpenNode={openNode} {...extra} />
    </MemoryRouter>,
  );
  return { apply, openNode };
}

describe("이슈 패널 묶음·정보 (5.7R.38)", () => {
  it("정보 이슈는 접힌 묶음에 있고 펼치면 한 행으로 묶여 '첫 노드 외 N-1개'가 나온다", () => {
    const { apply, openNode } = setup(infos);
    expect(screen.queryByText("이 값은 쓰이지 않습니다")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /정보 3건/ }));
    expect(screen.getByText("이 값은 쓰이지 않습니다")).toBeTruthy();
    expect(screen.getByRole("button", { name: "구현자 외 2개" })).toBeTruthy();
    expect(screen.getAllByText("비워도 결과는 같습니다.")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "값 비우기 (3개)" }));
    const [, sug] = apply.mock.calls[0] as [Issue, { patch: { unset_node_fields: unknown[] } }];
    expect(sug.patch.unset_node_fields).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "노드 설정 열기" }));
    expect(openNode).toHaveBeenCalledWith("a", "/settings/x");
    fireEvent.click(screen.getByRole("button", { name: "대상 노드별 보기" }));
    expect(screen.getAllByRole("button", { name: "노드 설정 열기" })).toHaveLength(4);
  });

  it("정보 필터는 펼친 상태로 보이고 오류·경고 요약에 포함되지 않는다", () => {
    setup(infos);
    expect(screen.getByText(/검증 이슈 \(오류 0 · 경고 0 · 정보 3\)/)).toBeTruthy();
    expect(screen.getByText("문제 없음 ✓ · 정보 3")).toBeTruthy();
    fireEvent.click(within(screen.getByRole("group", { name: "심각도 필터" })).getByRole("button", { name: /^정보/ }));
    expect(screen.getByText("이 값은 쓰이지 않습니다")).toBeTruthy();
  });

  it("group이 없는 이슈는 기존 행 그대로고 코드가 보인다", () => {
    setup([{ severity: "error", code: "x.err", message: "오류 하나", node_id: "a" } as unknown as Issue]);
    expect(screen.getByText("x.err")).toBeTruthy();
    expect(screen.getByText("오류 하나")).toBeTruthy();
  });

  it("미리보기(팀 목록·카드 펼침)는 info를 세지도 보이지도 않는다", () => {
    const { shown, rest } = previewIssues([...infos, { severity: "warning", code: "w", message: "w" } as unknown as Issue], false);
    expect(shown).toHaveLength(1);
    expect(rest).toBe(0);
  });
});

describe("무시되는 필드 이유 줄 (5.7R.38 F5)", () => {
  it("위임자·방식 이름을 문구에 넣는다", () => {
    const g = { id: "g", name: "g", nodes: [{ id: "l", type: "t", label: "리더" }, { id: "w", type: "t" }], edges: [{ id: "e", kind: "k", source: { node: "l", port: "o" }, target: { node: "w", port: "i" }, config: { strategy: "s1" } }] } as unknown as Graph;
    const out = ignoredFieldReasons(["/backend_options"], "w", g, [{ id: "k", invocation: {} }] as never, [{ id: "s1", title: "서브에이전트" }] as never);
    expect(out["/backend_options"]).toBe("이 위임 방식(서브에이전트)에서는 리더의 값을 씁니다");
  });

  it("노드 덮어쓰기 값이 있을 때만 [비우기]가 나온다", () => {
    const onClear = vi.fn();
    render(<IgnoredValueClear reasons={{ "/a": "이유", "/b": "이유" }} ownValue={{ a: 1 }} onClear={onClear} />);
    const btns = screen.getAllByRole("button", { name: "비우기" });
    expect(btns).toHaveLength(1);
    fireEvent.click(btns[0]!);
    expect(onClear).toHaveBeenCalledWith("/a");
  });
});
