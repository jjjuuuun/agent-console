import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Composer, resolveSendKey, type ComposerHandle, type ComposerProps } from "./Composer";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function setup(over: Partial<ComposerProps> = {}) {
  const onSend = vi.fn();
  const onChange = vi.fn();
  const utils = render(<Composer value="안녕하세요" onChange={onChange} onSend={onSend} {...over} />);
  const box = screen.getByRole("textbox", { name: "메시지 입력" });
  return { onSend, onChange, box, ...utils };
}

describe("Composer 전송 키", () => {
  it("Enter 전송, Shift+Enter는 전송하지 않는다", () => {
    const { onSend, box } = setup();
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
  });
  it("sendKey=ctrl_enter이면 Ctrl+Enter만 전송, 모르는 값은 Enter 전송", () => {
    const { onSend, box, rerender } = setup({ sendKey: "ctrl_enter" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(resolveSendKey("whatever")).toBe("enter");
    rerender(<Composer value="x" onChange={() => {}} onSend={onSend} sendKey="whatever" />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(2);
  });
  it("빈 입력·비활성·전송 중이면 전송하지 않는다", () => {
    const { onSend, box, rerender } = setup({ value: "  " });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "전송" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<Composer value="x" onChange={() => {}} onSend={onSend} sendDisabled />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });
  it("입력하면 onChange, 전송 버튼 클릭", () => {
    const { onSend, onChange, box } = setup();
    fireEvent.change(box, { target: { value: "새 값" } });
    expect(onChange).toHaveBeenCalledWith("새 값");
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    expect(onSend).toHaveBeenCalledTimes(1);
  });
});

describe("Composer 한글 IME", () => {
  it("조합 중 Enter는 전송하지 않는다 (compositionstart~end)", () => {
    const { onSend, box } = setup();
    fireEvent.compositionStart(box);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });
  it("isComposing, keyCode 229인 Enter도 무시한다", () => {
    const { onSend, box } = setup();
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 });
    expect(onSend).not.toHaveBeenCalled();
  });
  it("조합 확정 직후 같은 틱의 Enter는 무시하고, 다음 틱부터 전송한다", () => {
    vi.useFakeTimers();
    const { onSend, box } = setup();
    fireEvent.compositionStart(box);
    fireEvent.compositionEnd(box);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    act(() => {
      vi.runAllTimers();
    });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
  });
});

describe("Composer 답변 모드 (1R.31)", () => {
  const target = { label: "PL · 설계", kindTitle: "질문" };
  it("answerTarget이 있으면 띠와 [답하기], placeholder가 바뀐다", () => {
    const onSwitch = vi.fn();
    setup({ answerTarget: target, onSwitchToMessage: onSwitch });
    expect(screen.getByTestId("answer-strip").textContent).toContain("PL · 설계의 질문에 답하는 중");
    expect(screen.getByRole("button", { name: "답하기" })).toBeTruthy();
    expect(screen.getByPlaceholderText("답을 입력하세요…")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "새 메시지로 보내기" }));
    expect(onSwitch).toHaveBeenCalled();
  });
  it("message 모드: 띠가 새 메시지 모드로, [질문에 답하기]로 복귀, 버튼은 [전송]", () => {
    const onAnswer = vi.fn();
    setup({ answerTarget: target, answerMode: "message", onSwitchToAnswer: onAnswer });
    expect(screen.getByTestId("answer-strip").textContent).toContain("새 메시지 모드");
    expect(screen.getByRole("button", { name: "전송" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "질문에 답하기" }));
    expect(onAnswer).toHaveBeenCalled();
  });
  it("answerTarget이 없으면 띠가 없다", () => {
    setup();
    expect(screen.queryByTestId("answer-strip")).toBeNull();
  });
  it("Ctrl+Shift+Enter는 새 메시지로 보내기(onSendAsMessage 우선, 없으면 onSwitchToMessage)", () => {
    const asMsg = vi.fn();
    const sw = vi.fn();
    const onSend = vi.fn();
    const { box, rerender } = setup({ answerTarget: target, onSendAsMessage: asMsg, onSwitchToMessage: sw, onSend });
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true, shiftKey: true });
    expect(asMsg).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
    rerender(<Composer value="x" onChange={() => {}} onSend={onSend} answerTarget={target} onSwitchToMessage={sw} />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", ctrlKey: true, shiftKey: true });
    expect(sw).toHaveBeenCalledTimes(1);
  });
});

describe("Composer 기타", () => {
  it("사유·안내 줄·ref.focus·↑ 불러오기·Esc", () => {
    const ref = createRef<ComposerHandle>();
    const onRecall = vi.fn();
    const onEscape = vi.fn();
    render(<Composer ref={ref} value="" onChange={() => {}} onSend={() => {}} disabledReason="보관된 대화입니다" busyNotice={{ text: "대기열 안내", tone: "info" }} pendingHint="카드에서 답해 주세요 (2건 대기)" onRecallLast={onRecall} onEscape={onEscape} />);
    expect(screen.getByText("보관된 대화입니다")).toBeTruthy();
    expect(screen.getByText("대기열 안내")).toBeTruthy();
    expect(screen.getByText(/2건 대기/)).toBeTruthy();
    const box = screen.getByRole("textbox");
    act(() => ref.current?.focus());
    expect(document.activeElement).toBe(box);
    fireEvent.keyDown(box, { key: "ArrowUp" });
    expect(onRecall).toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Escape" });
    expect(onEscape).toHaveBeenCalled();
  });
  it("disabled면 입력창이 잠긴다", () => {
    setup({ disabled: true });
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(true);
  });
});

describe("Composer autoFocus", () => {
  it("처음에 비활성이면, 활성이 될 때 포커스를 준다", () => {
    const { box, rerender } = setup({ autoFocus: true, disabled: true });
    expect(document.activeElement).not.toBe(box);
    rerender(<Composer value="" onChange={() => {}} onSend={() => {}} autoFocus disabled={false} />);
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "메시지 입력" }));
  });
  it("다른 곳에 포커스가 있으면 빼앗지 않는다", () => {
    const other = document.createElement("button");
    document.body.appendChild(other);
    const { rerender } = setup({ autoFocus: true, disabled: true });
    other.focus();
    rerender(<Composer value="" onChange={() => {}} onSend={() => {}} autoFocus disabled={false} />);
    expect(document.activeElement).toBe(other);
    other.remove();
  });
});
