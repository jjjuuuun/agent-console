import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeDescriptor, makeInteraction } from "../fixtures";
import { decisionButtonStyle } from "./decisionStyle";
import { InteractionCard, type InteractionCardProps } from "./InteractionCard";
import type { RendererComponent } from "./types";

afterEach(cleanup);

/** 카드 루트(내장 <details>도 group 역할이라 data 속성으로 찾는다). */
const card = () => document.querySelector("[data-interaction-id]") as HTMLElement;

function setup(over: Partial<InteractionCardProps> = {}) {
  const onRespond = vi.fn().mockResolvedValue(undefined);
  const props: InteractionCardProps = {
    interaction: makeInteraction(),
    descriptor: makeDescriptor(),
    onRespond,
    now: 1012,
    actorLabel: "PL · 설계",
    ...over,
  };
  const utils = render(<InteractionCard {...props} />);
  return { onRespond, ...utils };
}

const questionPayload = {
  questions: [{ question: "어느 방식?", header: "방식", options: [{ label: "이메일", description: "메일로" }, { label: "소셜" }], multi_select: false }],
};

describe("렌더러 선택은 디스크립터 renderer 이름으로만 (R0.3)", () => {
  it("임의 종류 이름 + renderer=choices이면 선택 카드로 그린다", () => {
    setup({ interaction: makeInteraction({ kind: "anything-new", payload: questionPayload }), descriptor: makeDescriptor({ id: "anything-new", title: "새 종류", ui_hints: { renderer: "choices" } }) });
    expect(screen.getByRole("radiogroup")).toBeTruthy();
    expect(screen.getByText("새 종류", { exact: false })).toBeTruthy();
  });
  it("renderers prop으로 임의 renderer를 더한다", () => {
    const Custom: RendererComponent = ({ interaction, onSubmit }) => (
      <button type="button" onClick={() => onSubmit({ got: interaction.kind })}>
        커스텀
      </button>
    );
    const { onRespond } = setup({ descriptor: makeDescriptor({ ui_hints: { renderer: "my-renderer" } }), renderers: { "my-renderer": Custom } });
    fireEvent.click(screen.getByText("커스텀"));
    expect(onRespond).toHaveBeenCalledWith({ got: "kind-x" });
  });
  it("모르는 renderer는 renderFallback으로 넘기고 인자를 준다", () => {
    const renderFallback = vi.fn(() => <div>폴백 폼</div>);
    setup({ descriptor: makeDescriptor({ ui_hints: { renderer: "unknown-r" } }), renderFallback });
    expect(screen.getByText("폴백 폼")).toBeTruthy();
    expect(renderFallback).toHaveBeenCalledWith(expect.objectContaining({ submitting: false, onSubmit: expect.any(Function), errors: [] }));
  });
  it("descriptor가 없으면 종류 원문을 title로, renderer 없음은 폴백", () => {
    setup({ interaction: makeInteraction({ kind: "raw-kind-id" }), descriptor: undefined, renderFallback: () => <div>F</div> });
    expect(screen.getByText("raw-kind-id")).toBeTruthy();
    expect(screen.getByText("F")).toBeTruthy();
  });
  it("renderers 키가 Object 프로토타입 이름이어도 안전하게 폴백", () => {
    setup({ descriptor: makeDescriptor({ ui_hints: { renderer: "constructor" } }), renderFallback: () => <div>안전 폴백</div> });
    expect(screen.getByText("안전 폴백")).toBeTruthy();
  });
  it("내장 JSON 폴백: 잘못된 JSON은 보내기 비활성, 올바르면 응답 전송", async () => {
    const { onRespond } = setup({ interaction: makeInteraction({ payload: { a: 1 } }) });
    const box = screen.getByLabelText("응답(JSON)");
    fireEvent.change(box, { target: { value: "{x" } });
    expect((screen.getByRole("button", { name: "보내기" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(box, { target: { value: '{"ok":true}' } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ ok: true }));
  });
});

describe("공통 프레임", () => {
  it("role=group, 접근성 이름, 요청자 표기, data-status=waiting, 대기 시간·남은 시간", () => {
    setup({ interaction: makeInteraction({ expires_at: 1300 }) });
    const g = screen.getByRole("group", { name: "임의 종류, PL · 설계, 응답 대기" });
    expect(g.getAttribute("data-status")).toBe("waiting");
    expect(screen.getByText("PL · 설계", { exact: false })).toBeTruthy();
    expect(screen.getByText("응답 대기 12초")).toBeTruthy();
    expect(screen.getByText("남은 시간 4:48")).toBeTruthy();
  });
  it("남은 시간 1분 미만은 경고 표시", () => {
    setup({ interaction: makeInteraction({ expires_at: 1030 }) });
    expect(screen.getByText(/▲ 남은 시간 0:18/)).toBeTruthy();
  });
  it("title·message를 본문 위에 보인다", () => {
    setup({ interaction: makeInteraction({ title: "제목", message: "**굵은** 안내" }) });
    expect(screen.getByText("제목")).toBeTruthy();
    expect(document.querySelector("strong")?.textContent).toBe("굵은");
  });
  it("낙관적으로 접지 않는다: 응답이 성공해도 카드는 props가 바뀌기 전까지 대기 상태", async () => {
    const { onRespond } = setup({ interaction: makeInteraction({ payload: { a: 1 } }) });
    fireEvent.change(screen.getByLabelText("응답(JSON)"), { target: { value: "{}" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(onRespond).toHaveBeenCalled());
    expect(card().getAttribute("data-card-state")).toBe("pending");
    expect(card().getAttribute("data-status")).toBe("waiting");
  });
  it("전송 중에는 aria-busy, onRespond가 reject되면 오류 영역에 메시지", async () => {
    let reject: (e: Error) => void = () => {};
    const onRespond = vi.fn(() => new Promise<void>((_, r) => (reject = r)));
    setup({ onRespond, interaction: makeInteraction({ payload: {} }) });
    fireEvent.change(screen.getByLabelText("응답(JSON)"), { target: { value: "{}" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(card().getAttribute("aria-busy")).toBe("true"));
    reject(new Error("이미 답한 요청"));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("이미 답한 요청"));
    expect(card().getAttribute("aria-busy")).toBeNull();
  });
  it("422 errors를 오류 영역에 보인다", () => {
    setup({ errors: [{ path: "/answers", message: "필수 값" }] });
    expect(screen.getByRole("alert").textContent).toContain("/answers: 필수 값");
  });
  it("disabled면 입력이 막히고 연결 끊김 칩", () => {
    setup({ disabled: true, descriptor: makeDescriptor({ ui_hints: { renderer: "choices" } }), interaction: makeInteraction({ payload: questionPayload }) });
    expect(screen.getByText("연결 끊김")).toBeTruthy();
    expect((screen.getAllByRole("radio")[0] as HTMLButtonElement).disabled).toBe(true);
  });
  it("Esc는 onEscape, autoFocus는 첫 입력 요소", () => {
    const onEscape = vi.fn();
    setup({ onEscape, autoFocus: true, descriptor: makeDescriptor({ ui_hints: { renderer: "choices" } }), interaction: makeInteraction({ payload: questionPayload }) });
    expect(document.activeElement?.getAttribute("role")).toBe("radio");
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(onEscape).toHaveBeenCalled();
  });
});

describe("choices 렌더러", () => {
  const d = makeDescriptor({ ui_hints: { renderer: "choices" } });
  it("단일 선택: 선택 후 [보내기]를 눌러야 전송, 선택 전에는 비활성", async () => {
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload: questionPayload }) });
    const send = screen.getByRole("button", { name: "보내기" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: /소셜/ }));
    expect(onRespond).not.toHaveBeenCalled();
    fireEvent.click(send);
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ answers: { "어느 방식?": "소셜" } }));
  });
  it("복수 선택 + 직접 입력, 숫자키, 라벨 배열로 응답", async () => {
    const payload = { questions: [{ question: "무엇?", options: [{ label: "A" }, { label: "B" }], multi_select: true }] };
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    expect(screen.getByRole("group", { name: "무엇?" })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("checkbox", { name: /A/ }), { key: "1" });
    fireEvent.keyDown(screen.getByRole("checkbox", { name: /B/ }), { key: "2" });
    fireEvent.click(screen.getByRole("checkbox", { name: /직접 입력/ }));
    fireEvent.change(screen.getByPlaceholderText("직접 입력"), { target: { value: "기타 의견" } });
    fireEvent.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ answers: { "무엇?": ["A", "B", "기타 의견"] } }));
  });
  it("단일 선택에서 직접 입력은 다른 선택을 해제한다", () => {
    setup({ descriptor: d, interaction: makeInteraction({ payload: questionPayload }) });
    fireEvent.click(screen.getByRole("radio", { name: /이메일/ }));
    fireEvent.click(screen.getByRole("radio", { name: /직접 입력/ }));
    expect(screen.getByRole("radio", { name: /이메일/ }).getAttribute("aria-checked")).toBe("false");
  });
  it("여러 질문: 모두 답해야 활성, 선택지 없는 질문은 텍스트 입력", async () => {
    const payload = { questions: [{ question: "Q1", options: [{ label: "x" }], multi_select: false }, { question: "Q2", options: [], multi_select: false }] };
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    const send = screen.getByRole("button", { name: "보내기" }) as HTMLButtonElement;
    fireEvent.click(screen.getByRole("radio", { name: /x/ }));
    expect(send.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Q2"), { target: { value: "자유 답" } });
    expect(send.disabled).toBe(false);
    fireEvent.click(send);
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ answers: { Q1: "x", Q2: "자유 답" } }));
  });
  it("한글 IME: 조합 중 Ctrl+Enter는 전송하지 않고, 확정 후에는 전송", async () => {
    const payload = { questions: [{ question: "이름?", options: [], multi_select: false }] };
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    const box = screen.getByLabelText("이름?");
    fireEvent.change(box, { target: { value: "한글" } });
    fireEvent.compositionStart(box);
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true, isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true, keyCode: 229 });
    expect(onRespond).not.toHaveBeenCalled();
    fireEvent.compositionEnd(box);
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ answers: { "이름?": "한글" } }));
  });
  it("답함 접힌 줄 요약과 펼침(읽기 전용, 선택 표시)", () => {
    setup({
      descriptor: d,
      interaction: makeInteraction({ status: "answered", payload: questionPayload, response: { answers: { "어느 방식?": "이메일" } }, closed_at: 1012, answered_by: "timeout" }),
    });
    const toggle = screen.getByRole("button", { name: /임의 종류/ });
    expect(toggle.textContent).toContain("답함: 이메일 · 12초");
    expect(toggle.textContent).toContain("시간 초과");
    expect(card().getAttribute("data-status")).toBe("succeeded");
    fireEvent.click(toggle);
    expect(screen.getByRole("radio", { name: /이메일/ }).getAttribute("aria-checked")).toBe("true");
    expect((screen.getByRole("radio", { name: /이메일/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "보내기" })).toBeNull();
  });
});

describe("permission 렌더러", () => {
  const d = makeDescriptor({ ui_hints: { renderer: "permission" } });
  const payload = { tool_name: "Bash", input_preview: { command: "ls" }, description: "목록", decision_reason: "정책", blocked_path: "/tmp/a" };
  it("본문 표시와 허용·이번 실행 동안 허용 응답", async () => {
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    expect(screen.getByText("‘Bash’ 도구를 실행하려고 합니다")).toBeTruthy();
    expect(screen.getByText("이유: 정책")).toBeTruthy();
    expect(screen.getByText("경로: /tmp/a")).toBeTruthy();
    expect(screen.getByTestId("input-preview").textContent).toContain('"command": "ls"');
    fireEvent.click(screen.getByRole("button", { name: /^허용/ }));
    await waitFor(() => expect(onRespond).toHaveBeenLastCalledWith({ decision: "allow" }));
    fireEvent.click(screen.getByRole("button", { name: /이번 실행 동안 허용/ }));
    await waitFor(() => expect(onRespond).toHaveBeenLastCalledWith({ decision: "allow_for_run" }));
  });
  it("거부는 한 번 더: 사유 입력을 연 뒤 [거부 보내기]", async () => {
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    fireEvent.click(screen.getByRole("button", { name: /^거부/ }));
    expect(onRespond).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("거부 사유(선택)"), { target: { value: "위험함" } });
    fireEvent.click(screen.getByRole("button", { name: "거부 보내기" }));
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ decision: "deny", message: "위험함" }));
  });
  it("Y·A·N 단축키는 카드 안에서만, 입력 요소 안에서는 무시", async () => {
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    fireEvent.keyDown(screen.getByRole("button", { name: /^허용/ }), { key: "y" });
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ decision: "allow" }));
    fireEvent.keyDown(screen.getByRole("button", { name: /^거부/ }), { key: "n" });
    const reason = screen.getByLabelText("거부 사유(선택)");
    onRespond.mockClear();
    fireEvent.keyDown(reason, { key: "y" });
    expect(onRespond).not.toHaveBeenCalled();
  });
  it("editable_input이 있을 때만 '입력 고쳐서 허용' — JSON 오류면 비활성", async () => {
    const { onRespond, unmount } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    expect(screen.queryByText(/입력 고쳐서 허용/)).toBeNull();
    unmount();
    const r = setup({ descriptor: d, interaction: makeInteraction({ payload: { ...payload, editable_input: { command: "ls" } } }) });
    fireEvent.click(screen.getByRole("button", { name: /입력 고쳐서 허용/ }));
    const box = screen.getByLabelText("입력 고쳐서 허용");
    fireEvent.change(box, { target: { value: "{" } });
    expect((screen.getByRole("button", { name: "수정해서 허용" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(box, { target: { value: '{"command":"pwd"}' } });
    fireEvent.click(screen.getByRole("button", { name: "수정해서 허용" }));
    await waitFor(() => expect(r.onRespond).toHaveBeenCalledWith({ decision: "allow", updated_input: { command: "pwd" } }));
    expect(onRespond).not.toHaveBeenCalled();
  });
  it("ui_hints.decision_map으로 응답 값을 바꾼다", async () => {
    const { onRespond } = setup({ descriptor: makeDescriptor({ ui_hints: { renderer: "permission", decision_map: { allow: "yes" } } }), interaction: makeInteraction({ payload }) });
    fireEvent.click(screen.getByRole("button", { name: /^허용/ }));
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ decision: "yes" }));
  });
  it("답함 요약: 거부 사유 한 줄", () => {
    setup({ descriptor: d, interaction: makeInteraction({ status: "answered", payload, response: { decision: "deny", message: "싫어\n둘째" }, closed_at: 1003 }) });
    expect(screen.getByRole("button", { name: /임의 종류/ }).textContent).toContain("거부: 싫어 · 3초");
  });
});

describe("review 렌더러", () => {
  const d = makeDescriptor({ ui_hints: { renderer: "review" } });
  const decisions = [
    { id: "go", label: "진행", edit: false, feedback: false },
    { id: "fix", label: "수정", edit: true, feedback: true },
  ];
  const payload = { content: "# 초안\n본문", source_node: "작성", decisions };
  it("결정 버튼은 payload 순서·라벨, 힌트가 없으면 모두 같은 스타일", () => {
    setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    const [a, b] = [screen.getByRole("button", { name: /진행/ }), screen.getByRole("button", { name: /수정/ })];
    expect(a.getAttribute("style")?.replace(/\s/g, "")).toBe(b.getAttribute("style")?.replace(/\s/g, ""));
    expect(a.getAttribute("data-color")).toBeNull();
    expect(screen.getByText("작성의 결과")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^확정/ })).toBeNull();
  });
  it("선택 → 확정 버튼 → 응답. 편집/의견 필드는 결정 속성에 따라", async () => {
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    fireEvent.click(screen.getByRole("button", { name: /수정/ }));
    expect(screen.getByLabelText("의견")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("내용 수정"), { target: { value: "고친 본문" } });
    fireEvent.change(screen.getByLabelText("의견"), { target: { value: "좋아요" } });
    fireEvent.click(screen.getByRole("button", { name: "확정: 수정" }));
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ decision: "fix", edited: "고친 본문", feedback: "좋아요" }));
  });
  it("수정하지 않으면 edited를 생략, 선택 결정에서 Enter 한 번 더로 확정", async () => {
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload }) });
    const go = screen.getByRole("button", { name: /진행/ });
    fireEvent.click(go);
    fireEvent.keyDown(go, { key: "Enter" });
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ decision: "go" }));
  });
  it("숫자키로 결정 선택, 임의 결정 id도 동작", async () => {
    const payload2 = { content: "x", decisions: [{ id: "zzz", label: "임의", edit: false, feedback: false }] };
    const { onRespond } = setup({ descriptor: d, interaction: makeInteraction({ payload: payload2 }) });
    const btn = document.querySelector('[data-decision="zzz"]') as HTMLElement;
    fireEvent.keyDown(btn, { key: "1" });
    fireEvent.keyDown(btn, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(onRespond).toHaveBeenCalledWith({ decision: "zzz" }));
  });
  it("ui_hints: 토큰 이름은 색, 임의 CSS 색·모르는 이름은 무시, dashed는 점선", () => {
    const hinted = [
      { id: "a", label: "A", ui_hints: { color: "success", icon: "✓" } },
      { id: "b", label: "B", ui_hints: { color: "#ff0000" } },
      { id: "c", label: "C", ui_hints: { color: "rainbow", dashed: true } },
    ];
    setup({ descriptor: d, interaction: makeInteraction({ payload: { content: "x", decisions: hinted } }) });
    const a = screen.getByRole("button", { name: /A/ });
    expect(a.getAttribute("data-color")).toBe("success");
    expect(a.style.borderColor).toContain("--ac-success");
    expect(a.style.fontWeight).toBe("600");
    expect(a.textContent).toContain("✓");
    expect(screen.getByRole("button", { name: /B/ }).getAttribute("data-color")).toBeNull();
    expect(screen.getByRole("button", { name: /B/ }).style.borderColor).not.toContain("ff0000");
    expect(screen.getByRole("button", { name: /C/ }).style.borderStyle).toBe("dashed");
    expect(screen.getByRole("button", { name: /C/ }).style.fontWeight).toBe("");
  });
  it("decisionButtonStyle: 힌트 없음은 선택돼도 라벨 의미 없이 accent 테두리만", () => {
    expect(decisionButtonStyle(undefined, false).style.borderColor).toContain("--ac-border-strong");
    expect(decisionButtonStyle(null, true).style.borderColor).toContain("--ac-accent");
  });
  it("답함 요약과 읽기 전용 상세", () => {
    setup({ descriptor: d, interaction: makeInteraction({ status: "answered", payload, response: { decision: "fix", edited: "E", feedback: "f" }, closed_at: 1120 }) });
    const toggle = screen.getByRole("button", { name: /임의 종류/ });
    expect(toggle.textContent).toContain("수정 · 수정함 · 의견 있음");
    expect(toggle.textContent).toContain("2분");
  });
});

describe("상태별 표시", () => {
  const d = makeDescriptor({ ui_hints: { renderer: "choices" } });
  it("만료(timeout): 접힌 한 줄 + skipped, 펼치면 전달 안내", () => {
    setup({ descriptor: d, interaction: makeInteraction({ status: "expired", close_reason: "timeout", payload: questionPayload, closed_at: 1300 }) });
    expect(card().getAttribute("data-status")).toBe("skipped");
    expect(screen.getByRole("button", { name: /임의 종류/ }).textContent).toContain("만료됨 — 응답 없음 · 5분");
    fireEvent.click(screen.getByRole("button", { name: /임의 종류/ }));
    expect(screen.getByText("에이전트에게 ‘응답 없음’이 전달되었습니다")).toBeTruthy();
  });
  it("취소: 사유 표시", () => {
    setup({ descriptor: d, interaction: makeInteraction({ status: "cancelled", close_reason: "node_finished", payload: questionPayload }) });
    expect(card().getAttribute("data-status")).toBe("cancelled");
    expect(screen.getByRole("button", { name: /임의 종류/ }).textContent).toContain("취소됨 — 노드 종료");
  });
  it("서버 재시작 끊김: 배너 + 읽기 전용 + [답을 새 메시지로 보내기]", () => {
    const onResend = vi.fn();
    setup({ descriptor: d, serverRestartHint: { onResendAsMessage: onResend }, interaction: makeInteraction({ status: "expired", close_reason: "interrupted", payload: questionPayload }) });
    expect(screen.getByText("서버가 다시 시작되어 응답 대기가 끊겼습니다")).toBeTruthy();
    expect(card().getAttribute("data-status-kind")).toBe("run");
    expect((screen.getAllByRole("radio")[0] as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "답을 새 메시지로 보내기" }));
    expect(onResend).toHaveBeenCalled();
  });
  it("끊김 카드에 serverRestartHint가 없으면 버튼이 없다", () => {
    setup({ descriptor: d, interaction: makeInteraction({ status: "expired", close_reason: "interrupted", payload: questionPayload }) });
    expect(screen.queryByRole("button", { name: "답을 새 메시지로 보내기" })).toBeNull();
  });
  it("messages로 문구를 바꾼다", () => {
    setup({ messages: { waitingFor: "Waiting {duration}" } });
    expect(screen.getByText("Waiting 12초")).toBeTruthy();
  });
});
