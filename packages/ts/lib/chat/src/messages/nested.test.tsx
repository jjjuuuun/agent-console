import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { agentView, makeTurn } from "../fixtures";
import { InteractionCard } from "../interaction/InteractionCard";
import { makeDescriptor, makeInteraction } from "../fixtures";
import { ReplyGroup } from "./ReplyGroup";
import { TurnView } from "./TurnView";
import type { ProgressStep } from "./types";

afterEach(cleanup);

describe("TurnView: 중첩 팀·실패 처리 확장", () => {
  const failed = makeTurn({ status: "failed" });
  it("errorAction이 있으면 오류 블록 단추가 그 실행으로 가고 문구도 바뀐다", () => {
    const onOpenRun = vi.fn();
    render(<TurnView turn={failed} replyDisplay="separate" agentView={agentView} errorText="실패했습니다" onOpenRun={onOpenRun} errorAction={{ label: "자식 실행에서 원인 보기", runId: "child-1" }} />);
    fireEvent.click(screen.getByRole("button", { name: "자식 실행에서 원인 보기" }));
    expect(onOpenRun).toHaveBeenCalledWith("child-1");
  });
  it("errorAction이 없으면 기존처럼 이 턴의 실행으로 간다", () => {
    const onOpenRun = vi.fn();
    render(<TurnView turn={failed} replyDisplay="separate" agentView={agentView} errorText="실패했습니다" onOpenRun={onOpenRun} />);
    const buttons = within(screen.getByRole("alert")).getAllByRole("button");
    fireEvent.click(buttons[0]!);
    expect(onOpenRun).toHaveBeenCalledWith(failed.run_id);
  });
  it("푸터에 앱이 정한 muted 문구를 더한다", () => {
    render(<TurnView turn={makeTurn()} replyDisplay="separate" agentView={agentView} footerNote="실패 1건 처리됨" />);
    expect(screen.getByText(/실패 1건 처리됨/)).toBeTruthy();
  });
  it("진행 줄 칩의 openTarget이 있으면 그 실행·노드·연결로 연다", () => {
    const onOpenRun = vi.fn();
    const steps: ProgressStep[] = [
      { key: "k1", status: "succeeded", fromLabel: "가", toLabel: "나", methodLabel: "방식", indent: 0, href: "/x", openTarget: { runId: "child-1", nodeId: "nn" } },
      { key: "k2", status: "succeeded", fromLabel: "다", toLabel: "라", methodLabel: "방식", indent: 0, href: "/y", openTarget: { edgeId: "ee" } },
    ];
    render(<TurnView turn={makeTurn({ status: "completed" })} replyDisplay="separate" agentView={agentView} progress={steps} onOpenRun={onOpenRun} />);
    fireEvent.click(screen.getByRole("button", { name: /진행/ }));
    const links = screen.getAllByRole("link");
    fireEvent.click(links[0]!);
    expect(onOpenRun).toHaveBeenLastCalledWith("child-1", "nn", undefined);
    fireEvent.click(links[1]!);
    expect(onOpenRun).toHaveBeenLastCalledWith(makeTurn().run_id, undefined, "ee");
  });
});

describe("InteractionCard: contextChip", () => {
  it("칩 문구를 요청자 옆에 그리고, 링크·버튼·텍스트 세 모양을 지원한다", () => {
    const onClick = vi.fn();
    const { rerender } = render(<InteractionCard interaction={makeInteraction()} descriptor={makeDescriptor()} onRespond={async () => {}} now={1012} actorLabel="검토 › PL" contextChip={{ text: "중첩 팀", title: "검토 안의 요청" }} />);
    expect(screen.getByText("중첩 팀").getAttribute("title")).toBe("검토 안의 요청");
    rerender(<InteractionCard interaction={makeInteraction()} descriptor={makeDescriptor()} onRespond={async () => {}} now={1012} contextChip={{ text: "자식 실행 r-1", href: "/runs/r-1" }} />);
    expect(screen.getByRole("link", { name: "자식 실행 r-1" }).getAttribute("href")).toBe("/runs/r-1");
    rerender(<InteractionCard interaction={makeInteraction()} descriptor={makeDescriptor()} onRespond={async () => {}} now={1012} contextChip={{ text: "버튼 칩", onClick }} />);
    fireEvent.click(screen.getByRole("button", { name: "버튼 칩" }));
    expect(onClick).toHaveBeenCalled();
  });
  it("없으면 칩을 그리지 않는다", () => {
    render(<InteractionCard interaction={makeInteraction()} descriptor={makeDescriptor()} onRespond={async () => {}} now={1012} />);
    expect(document.querySelector("[data-part='context-chip']")).toBeNull();
  });
});

describe("ReplyGroup: 독립 위임 대상의 답변 머리", () => {
  const reply = [{ edge_id: "e1", node_id: "n1", agent_id: "a", final: true, text: "답" }];
  it("delegatedBy가 있으면 '{위임자}가 맡긴 {대상}', parentName(서브에이전트)보다 우선", () => {
    const { rerender } = render(<ReplyGroup replies={reply} display="separate" turnDone agentView={() => ({ name: "대상", delegatedBy: "위임자" })} />);
    expect(screen.getByText("위임자가 맡긴 대상")).toBeTruthy();
    rerender(<ReplyGroup replies={reply} display="separate" turnDone agentView={() => ({ name: "대상", parentName: "부모" })} />);
    expect(screen.getByText("부모 안의 대상")).toBeTruthy();
    rerender(<ReplyGroup replies={reply} display="separate" turnDone agentView={() => ({ name: "대상", parentName: "부모", delegatedBy: "위임자" })} />);
    expect(screen.getByText("위임자가 맡긴 대상")).toBeTruthy();
  });
});

describe("진행 줄 아바타", () => {
  it("fromAvatar·toAvatar가 있으면 칩 양 끝에 같은 아바타를 그린다", async () => {
    const { ProgressStrip } = await import("./ProgressStrip");
    const step: ProgressStep = {
      key: "k", status: "running", fromLabel: "가", toLabel: "나", methodLabel: "넘기기", indent: 0,
      fromAvatar: { id: "a", name: "가", text: "A", color: "#111111" },
      toAvatar: { id: "b", name: "나" },
    };
    const { container } = render(<ProgressStrip steps={[step]} collapsed={false} onToggle={() => {}} />);
    const avatars = Array.from(container.querySelectorAll("[data-avatar]")).map((e) => e.textContent);
    expect(avatars).toEqual(["A", "나"]);
  });
});
