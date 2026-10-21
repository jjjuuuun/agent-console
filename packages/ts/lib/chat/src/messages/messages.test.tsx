import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { agentView, makeInteraction, makeTurn } from "../fixtures";
import { Markdown, closeOpenFence } from "./Markdown";
import { MessageList } from "./MessageList";
import { ProgressStrip } from "./ProgressStrip";
import { ReplyGroup } from "./ReplyGroup";
import { showDuration } from "../shared/util";
import { normalizeReplyDisplay, selectVisibleReplies, sortReplies } from "./replyLogic";
import { TurnView } from "./TurnView";
import type { ProgressStep, ReplyItem } from "./types";

afterEach(cleanup);

const replies: ReplyItem[] = [
  { edge_id: "e2", node_id: "n2", agent_id: "b", order: 2, final: true, text: "최종 답" },
  { edge_id: "e1", node_id: "n1", agent_id: "a", order: 1, final: false, label: "초안", text: "중간 답\n둘째 줄" },
  { edge_id: "e3", node_id: "n3", agent_id: "c", final: false, text: "도착 순 꼴찌" },
];

describe("replyLogic", () => {
  it("모르는 값은 separate, 정렬은 order 오름차순 + 없음은 뒤", () => {
    expect(normalizeReplyDisplay("zzz")).toBe("separate");
    expect(normalizeReplyDisplay(undefined)).toBe("separate");
    expect(normalizeReplyDisplay("merged")).toBe("merged");
    expect(sortReplies(replies).map((r) => r.edge_id)).toEqual(["e1", "e2", "e3"]);
  });
  it("final_only는 final=false를 숨기고 개수를 센다", () => {
    const { visible, hidden } = selectVisibleReplies(replies, "final_only");
    expect(visible.map((r) => r.edge_id)).toEqual(["e2"]);
    expect(hidden).toBe(2);
  });
});

describe("ReplyGroup 세 방식", () => {
  const base = { agentView, turnDone: true } as const;
  it("separate: 답변마다 카드, 중간 결과는 완료 후 접힘(미리보기 1줄) + 점선", () => {
    render(<ReplyGroup {...base} replies={replies} display="separate" />);
    expect(screen.getAllByRole("region")).toHaveLength(3);
    expect(screen.getByText("최종 답")).toBeTruthy();
    expect(screen.queryByText("둘째 줄")).toBeNull();
    const dashed = document.querySelector('[data-intermediate="true"]') as HTMLElement;
    expect(dashed.className).toContain("ac-chat-reply"); // 점선 테두리는 CSS 클래스(styles.css)가 그린다
    fireEvent.click(screen.getAllByRole("button", { name: "펼치기" })[0]!);
    expect(screen.getByText(/둘째 줄/)).toBeTruthy();
  });
  it("separate: 실행 중에는 중간 결과가 펼쳐져 있다", () => {
    render(<ReplyGroup {...base} turnDone={false} replies={replies} display="separate" />);
    expect(screen.getByText(/둘째 줄/)).toBeTruthy();
  });
  it("merged: 카드 하나, 각 부분 머리 줄(label 또는 이름)", () => {
    render(<ReplyGroup {...base} replies={replies} display="merged" />);
    expect(screen.queryAllByRole("region")).toHaveLength(0);
    expect(document.querySelectorAll('[data-reply-display="merged"]')).toHaveLength(1);
    expect(screen.getByText("초안")).toBeTruthy();
    expect(screen.getByText("이름-b")).toBeTruthy();
  });
  it("final_only: 최종만, 숨긴 개수와 실행 상세 링크 (실행 중에도 숨김)", () => {
    const onOpenRun = vi.fn();
    render(<ReplyGroup {...base} turnDone={false} replies={replies} display="final_only" onOpenRun={onOpenRun} />);
    expect(screen.queryByText(/중간 답/)).toBeNull();
    expect(screen.getByText(/중간 결과 2개 숨김/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /실행 상세에서 보기/ }));
    expect(onOpenRun).toHaveBeenCalled();
  });
  it("스트리밍 답변에는 캐럿, 닫히지 않은 코드 펜스는 코드 블록으로", () => {
    render(<ReplyGroup {...base} turnDone={false} display="separate" replies={[{ edge_id: "e", node_id: "n", final: true, text: "```ts\nconst a = 1", streaming: true }]} />);
    expect(document.querySelector(".ac-caret")).toBeTruthy();
    expect(document.querySelector("pre")?.textContent).toContain("const a = 1");
  });
  it("제어형 expanded가 사용자 선택을 유지", () => {
    const onChange = vi.fn();
    render(<ReplyGroup {...base} replies={replies} display="separate" expanded={{ e1: true }} onExpandedChange={onChange} />);
    expect(screen.getByText(/둘째 줄/)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "접기" })[0]!);
    expect(onChange).toHaveBeenCalledWith({ e1: false });
  });
});

describe("Markdown", () => {
  it("원시 HTML은 렌더하지 않고 텍스트로 남긴다", () => {
    const { container } = render(<Markdown text={'<script>alert(1)</script> <b>굵게</b>'} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<script>");
  });
  it("http(s) 링크만 열리고 rel을 단다. javascript: 는 링크가 아니다", () => {
    const { container } = render(<Markdown text={"[좋음](https://example.com) [나쁨](javascript:alert(1))"} />);
    const anchors = container.querySelectorAll("a");
    expect(anchors).toHaveLength(1);
    expect(anchors[0]?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(anchors[0]?.getAttribute("target")).toBe("_blank");
  });
  it("closeOpenFence", () => {
    expect(closeOpenFence("a\n```js\nx")).toBe("a\n```js\nx\n```");
    expect(closeOpenFence("```\nx\n```")).toBe("```\nx\n```");
  });
});

describe("ProgressStrip", () => {
  const step = (i: number, over: Partial<ProgressStep> = {}): ProgressStep => ({ key: `s${i}`, status: "running", fromLabel: `A${i}`, toLabel: `B${i}`, methodLabel: "임의 방식", indent: 0, ...over });
  it("방식 라벨은 props 그대로, 점선·들여쓰기·클릭", () => {
    const onOpen = vi.fn();
    render(<ProgressStrip steps={[step(1, { methodDashed: true }), step(2, { indent: 1, status: "succeeded", durationMs: 18000 })]} collapsed={false} onToggle={() => {}} onOpen={onOpen} />);
    expect(screen.getAllByText("임의 방식")).toHaveLength(2);
    expect(document.querySelector('[data-dashed="true"]')).toBeTruthy();
    expect(screen.getByText(/완료 18초/)).toBeTruthy();
    fireEvent.click(screen.getByText("B2"));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ key: "s2" }));
  });
  it("접히면 요약 한 줄, 8개 초과면 최근 3개 + 외 N단계", () => {
    const steps = Array.from({ length: 10 }, (_, i) => step(i));
    const { rerender } = render(<ProgressStrip steps={steps.slice(0, 3)} collapsed onToggle={() => {}} />);
    expect(screen.queryByText("A0")).toBeNull();
    expect(screen.getByRole("button", { name: /진행 3단계/ })).toBeTruthy();
    rerender(<ProgressStrip steps={steps} collapsed onToggle={() => {}} />);
    expect(screen.getByText("…외 7단계")).toBeTruthy();
    expect(screen.getByText("A9")).toBeTruthy();
    expect(screen.queryByText("A6")).toBeNull();
  });
});

describe("TurnView / MessageList", () => {
  it("턴 구조: 사용자 메시지, 답변, 상호작용 카드(created_at 순), 푸터", () => {
    const turn = makeTurn({
      status: "waiting",
      started_at: 100,
      replies: [{ edge_id: "e", node_id: "n", agent_id: "pl", final: true, text: "초안" }],
      interactions: [makeInteraction({ id: "late", created_at: 20 }), makeInteraction({ id: "early", created_at: 10 })],
      usage: { total_tokens: 1204 },
    });
    render(<TurnView turn={turn} replyDisplay="separate" agentView={agentView} now={112} renderInteraction={(i) => <div data-testid="card">{i.id}</div>} onCancelTurn={() => {}} />);
    expect(screen.getByRole("article")).toBeTruthy();
    expect(screen.getAllByTestId("card").map((c) => c.textContent)).toEqual(["early", "late"]);
    // 응답 대기 카드가 보이는 동안 푸터는 대기 개수·경과 시간을 반복하지 않는다(§7.6)
    expect(screen.getByTestId("turn-status").textContent).toBe("응답 대기 중");
    expect(screen.queryByText(/12초/)).toBeNull();
    expect(screen.getByText(/토큰 1,204/)).toBeTruthy();
    expect(screen.getByText(/일부는 총 토큰만/)).toBeTruthy();
  });
  it("실행 중 턴에만 중지 버튼, 스트리밍 텍스트가 해당 노드 답변을 대신한다", () => {
    const onCancel = vi.fn();
    const turn = makeTurn({ status: "running", replies: [{ edge_id: "e", node_id: "n", final: true, text: "" }] });
    const { rerender } = render(<TurnView turn={turn} replyDisplay="separate" agentView={agentView} streaming={{ n: "스트림 중" }} onCancelTurn={onCancel} />);
    expect(screen.getByText("스트림 중")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /중지/ }));
    expect(onCancel).toHaveBeenCalledWith("r1");
    rerender(<TurnView turn={makeTurn()} replyDisplay="separate" agentView={agentView} onCancelTurn={onCancel} />);
    expect(screen.queryByRole("button", { name: /중지/ })).toBeNull();
  });
  it("실패 턴 오류 블록과 다시 보내기", () => {
    const onResend = vi.fn();
    render(<TurnView turn={makeTurn({ status: "failed" })} replyDisplay="separate" agentView={agentView} errorText="서버 오류" onResendText={onResend} />);
    expect(screen.getByRole("alert").textContent).toContain("서버 오류");
    fireEvent.click(screen.getByRole("button", { name: "다시 보내기" }));
    expect(onResend).toHaveBeenCalledWith("안녕");
  });
  it("messages로 문구를 바꾼다", () => {
    render(<TurnView turn={makeTurn()} replyDisplay="separate" agentView={agentView} messages={{ yourMessage: "Me", turnStatus: { completed: "Done" } }} />);
    expect(screen.getByRole("group", { name: "Me" })).toBeTruthy();
    expect(screen.getByTestId("turn-status").textContent).toBe("Done");
  });
  it("대기열 행, 처음 안내, 위로 스크롤 시 onLoadOlder", () => {
    const onLoadOlder = vi.fn();
    render(<MessageList turns={[makeTurn()]} replyDisplay="separate" agentView={agentView} queued={[{ key: "q", text: "다음 일", position: 2 }]} hasMore onLoadOlder={onLoadOlder} />);
    expect(screen.getByText("대기열 #2")).toBeTruthy();
    expect(screen.queryByText("대화의 처음입니다")).toBeNull();
    fireEvent.scroll(screen.getByRole("region", { name: "대화" }));
    expect(onLoadOlder).toHaveBeenCalledTimes(1);
  });
  it("대기열 취소 버튼은 onCancelQueued가 있을 때만", () => {
    const { rerender } = render(<MessageList turns={[]} replyDisplay="separate" agentView={agentView} queued={[{ key: "q", text: "x", position: 1 }]} />);
    expect(screen.queryByRole("button", { name: "대기열에서 빼기" })).toBeNull();
    const cancel = vi.fn();
    rerender(<MessageList turns={[]} replyDisplay="separate" agentView={agentView} queued={[{ key: "q", text: "x", position: 1 }]} onCancelQueued={cancel} />);
    fireEvent.click(screen.getByRole("button", { name: "대기열에서 빼기" }));
    expect(cancel).toHaveBeenCalledWith("q");
  });
  it("focusInteractionId로 지정한 카드에 포커스", () => {
    const turn = makeTurn({ status: "waiting", interactions: [makeInteraction({ id: "ix" })] });
    render(
      <MessageList
        turns={[turn]}
        replyDisplay="separate"
        agentView={agentView}
        focusInteractionId="ix"
        renderInteraction={(i) => (
          <div data-interaction-id={i.id}>
            <button type="button">첫 버튼</button>
          </div>
        )}
      />,
    );
    expect(document.activeElement?.textContent).toBe("첫 버튼");
  });
  it("위로 스크롤한 상태에서 새 내용이 오면 pill, 맨 아래면 따라간다", () => {
    const { rerender } = render(<MessageList turns={[makeTurn()]} replyDisplay="separate" agentView={agentView} />);
    const sc = screen.getByRole("region", { name: "대화" });
    Object.defineProperty(sc, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(sc, "clientHeight", { value: 100, configurable: true });
    sc.scrollTop = 0;
    fireEvent.scroll(sc);
    act(() => {
      rerender(<MessageList turns={[makeTurn(), makeTurn({ run_id: "r2" })]} replyDisplay="separate" agentView={agentView} />);
    });
    expect(screen.getByRole("button", { name: /새 내용/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /새 내용/ }));
    expect(screen.queryByRole("button", { name: /새 내용/ })).toBeNull();
  });
});

describe("ProgressStrip: 중첩·위임 칩", () => {
  const st = (key: string, over: Partial<ProgressStep> = {}): ProgressStep => ({ key, status: "running", fromLabel: `F-${key}`, toLabel: `T-${key}`, methodLabel: "임의 방식", indent: 0, ...over });
  const child = { runId: "child-1", href: "/x/child-1", nodeLabel: "중첩 노드", progress: { done: 2, total: 5 } };
  const nested: ProgressStep = st("team", { solo: true, toLabel: "▣ 임의 팀", child, children: [st("c1", { status: "succeeded", indent: 1 }), st("c2", { indent: 1, children: [st("g1", { indent: 2 })] })] });

  it("들여 쓰기 단계·배지·회차/호출 표기·경고 톤(글자 포함)", () => {
    render(<ProgressStrip steps={[st("a"), st("b", { indent: 1, badge: "임의 배지", iterationLabel: "2회차", callLabel: "호출 3", tone: "warning" })]} collapsed={false} onToggle={() => {}} />);
    const b = document.querySelector('[data-step="b"]') as HTMLElement;
    expect(b.getAttribute("data-indent")).toBe("1");
    expect(b.style.getPropertyValue("--ac-depth")).toBe("1");
    expect(b.textContent).toContain("임의 배지");
    expect(b.textContent).toContain("2회차");
    expect(b.textContent).toContain("호출 3");
    expect(b.textContent).toContain("▲");
    expect(b.textContent).toContain("주의");
    // 배지가 있는 들여 쓴 단계에는 '같은 세션' 안내를 붙이지 않는다
    expect(b.querySelector("[title]")).toBeNull();
  });
  it("5단계부터는 4단계 위치에 그린다", () => {
    render(<ProgressStrip steps={[st("a", { indent: 7 })]} collapsed={false} onToggle={() => {}} />);
    expect((document.querySelector('[data-step="a"]') as HTMLElement).style.getPropertyValue("--ac-depth")).toBe("4");
  });
  it("중첩 팀 칩: 기본 접힘, 진행 숫자·현재 노드, 누르면 펼침/접힘(aria-expanded)", () => {
    render(<ProgressStrip steps={[nested]} collapsed={false} onToggle={() => {}} />);
    expect(screen.queryByText("T-c1")).toBeNull();
    const toggle = screen.getByRole("button", { name: /▣ 임의 팀/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.textContent).toContain("노드 2/5");
    expect(toggle.textContent).toContain("현재: T-g1");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("T-c1")).toBeTruthy();
    expect(screen.queryByText("T-g1")).toBeNull(); // 안쪽 칩은 따로 접혀 있다
    fireEvent.click(screen.getByRole("button", { name: /T-c2/ }));
    expect(screen.getByText("T-g1")).toBeTruthy();
    expect(document.querySelector('[data-step="g1"]')?.getAttribute("data-indent")).toBe("2");
    fireEvent.click(toggle);
    expect(screen.queryByText("T-c1")).toBeNull();
  });
  it("진행 숫자는 child.progress가 있을 때만", () => {
    const n = { ...nested, child: { runId: "c", href: "/c", nodeLabel: "n" } };
    render(<ProgressStrip steps={[n]} collapsed={false} onToggle={() => {}} />);
    expect(screen.getByRole("button", { name: /▣ 임의 팀/ }).textContent).not.toContain("노드");
  });
  it("[실행 상세 ↗]는 별도 링크(탭 정지점)이고 콜백/href로 열린다", () => {
    const onOpenChild = vi.fn();
    render(<ProgressStrip steps={[nested]} collapsed={false} onToggle={() => {}} onOpenChild={onOpenChild} />);
    const link = document.querySelector('[data-part="child-link"]') as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/x/child-1");
    expect(link.getAttribute("aria-label")).toBe("중첩 노드 실행 상세");
    fireEvent.click(link);
    expect(onOpenChild).toHaveBeenCalledWith(child, expect.objectContaining({ key: "team" }));
  });
  it("제어형 펼침: expandedStepKeys/onStepToggle", () => {
    const onStepToggle = vi.fn();
    const { rerender } = render(<ProgressStrip steps={[nested]} collapsed={false} onToggle={() => {}} expandedStepKeys={[]} onStepToggle={onStepToggle} />);
    fireEvent.click(screen.getByRole("button", { name: /▣ 임의 팀/ }));
    expect(onStepToggle).toHaveBeenCalledWith("team", true);
    expect(screen.queryByText("T-c1")).toBeNull();
    rerender(<ProgressStrip steps={[nested]} collapsed={false} onToggle={() => {}} expandedStepKeys={["team"]} />);
    expect(screen.getByText("T-c1")).toBeTruthy();
  });
  it("단계 수와 8개 초과 요약은 후손까지 편 전체 기준", () => {
    const kids = Array.from({ length: 9 }, (_, i) => st(`k${i}`, { indent: 1 }));
    const { rerender } = render(<ProgressStrip steps={[st("p", { solo: true, children: kids })]} collapsed onToggle={() => {}} />);
    expect(screen.getByRole("button", { name: /진행 10단계/ })).toBeTruthy();
    expect(screen.getByText("…외 7단계")).toBeTruthy();
    expect(screen.getByText("T-k8")).toBeTruthy();
    expect(screen.queryByText("T-k5")).toBeNull();
    rerender(<ProgressStrip steps={[st("p", { solo: true, children: kids.slice(0, 2) })]} collapsed onToggle={() => {}} />);
    expect(screen.getByRole("button", { name: /진행 3단계/ })).toBeTruthy();
  });
});

describe("5.2R.21 채팅 턴", () => {
  const st = (key: string, over: Partial<ProgressStep> = {}): ProgressStep => ({ key, status: "succeeded", fromLabel: `F-${key}`, toLabel: `T-${key}`, methodLabel: "방식", indent: 0, ...over });
  it("showDuration: 1초 미만·없음은 null, 그 외는 formatSeconds", () => {
    expect(showDuration(undefined)).toBeNull();
    expect(showDuration(0)).toBeNull();
    expect(showDuration(999)).toBeNull();
    expect(showDuration(1000)).toBe("1초");
    expect(showDuration(125000)).toBe("2분 5초");
  });
  it("진행 요약: 실행 중이면 '지금: 이름 상태'가 붙고, 0초는 그리지 않는다", () => {
    render(<ProgressStrip steps={[st("a", { durationMs: 0 }), st("b", { status: "running" })]} collapsed onToggle={() => {}} />);
    const summary = screen.getByRole("button", { name: /진행 2단계/ });
    expect(summary.textContent).toContain("지금: T-b 작업 중");
    expect(summary.textContent).not.toContain("0초");
    expect(document.querySelectorAll("[data-step]")).toHaveLength(1); // 현재 단계 1줄만
  });
  it("완료된 진행은 요약만, 1초 이상이면 소요 시간 포함, 행 소요는 1초 이상만", () => {
    const { rerender } = render(<ProgressStrip steps={[st("a", { durationMs: 400 }), st("b", { durationMs: 3000 })]} collapsed onToggle={() => {}} />);
    expect(screen.getByRole("button", { name: /진행 2단계 · 3초/ })).toBeTruthy();
    expect(document.querySelectorAll("[data-step]")).toHaveLength(0);
    rerender(<ProgressStrip steps={[st("a", { durationMs: 400 }), st("b", { durationMs: 3000 })]} collapsed={false} onToggle={() => {}} />);
    expect(document.querySelector('[data-step="a"]')!.textContent).not.toContain("0초");
    expect(document.querySelector('[data-step="b"]')!.textContent).toContain("완료 3초");
  });
  it("자식 실행 링크는 아이콘 하나(글자 없음)이고 이름·툴팁이 있다", () => {
    const child = { runId: "c", href: "/c", nodeLabel: "N" };
    render(<ProgressStrip steps={[st("t", { solo: true, child })]} collapsed={false} onToggle={() => {}} />);
    const link = document.querySelector('[data-part="child-link"]')!;
    expect(link.textContent).toBe("");
    expect(link.getAttribute("title")).toBe("자식 실행 열기");
  });
  it("내 메시지: 오른쪽 말풍선(나 라벨 없음), 복사·다시 보내기는 아이콘 단추", () => {
    const onResend = vi.fn();
    render(<TurnView turn={makeTurn({ started_at: 100 })} replyDisplay="separate" agentView={agentView} onResendText={onResend} formatTime={() => "10:32"} />);
    expect(screen.queryByText("나")).toBeNull();
    expect(screen.getByRole("group", { name: "나의 메시지" }).textContent).toBe("안녕");
    expect(screen.getByText("10:32").tagName).toBe("TIME");
    const copy = screen.getByRole("button", { name: "복사" });
    expect(copy.textContent).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "다시 보내기" }));
    expect(onResend).toHaveBeenCalledWith("안녕");
  });
  it("실행 상세 링크는 턴당 하나(답변 머리에 없다)", () => {
    const turn = makeTurn({ replies: [{ edge_id: "e", node_id: "n", agent_id: "pl", final: true, text: "답" }, { edge_id: "e2", node_id: "n2", agent_id: "pl", final: true, text: "답2" }] });
    render(<TurnView turn={turn} replyDisplay="separate" agentView={agentView} onOpenRun={() => {}} />);
    expect(screen.getAllByRole("button", { name: /^실행 상세/ })).toHaveLength(1);
  });
  it("푸터 소요 시간: 1초 미만이면 숨긴다", () => {
    render(<TurnView turn={makeTurn({ started_at: 100, ended_at: 100.4 })} replyDisplay="separate" agentView={agentView} />);
    expect(screen.queryByText(/0초/)).toBeNull();
  });
  it("턴 키보드: 포커스 가능, C 복사·R 다시 보내기, MessageList ↑↓ 이동", () => {
    const onResend = vi.fn();
    render(<MessageList turns={[makeTurn(), makeTurn({ run_id: "r2", user_text: "둘" })]} replyDisplay="separate" agentView={agentView} onResendText={onResend} />);
    const [a, b] = screen.getAllByRole("article");
    a!.focus();
    fireEvent.keyDown(a!, { key: "r" });
    expect(onResend).toHaveBeenCalledWith("안녕");
    fireEvent.keyDown(a!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(b);
    fireEvent.keyDown(b!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(a);
  });
});
