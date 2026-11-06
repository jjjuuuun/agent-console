import { EditorView } from "@codemirror/view";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TextEditor, jsonParseError, resolveLanguage, type TextEditorHandle, type TextEditorStatus } from "./index";

afterEach(cleanup);

function viewOf(container: HTMLElement): EditorView {
  const dom = container.querySelector<HTMLElement>(".cm-editor");
  const v = dom && EditorView.findFromDOM(dom);
  if (!v) throw new Error("편집기 없음");
  return v;
}

describe("TextEditor", () => {
  it("값을 보여 주고 접근성 이름과 data-ac-editable을 가진다", () => {
    const { container } = render(<TextEditor value="안녕 세계" ariaLabel="본문 편집기" />);
    const box = screen.getByRole("textbox", { name: "본문 편집기" });
    expect(box.getAttribute("data-ac-editable")).toBe("");
    expect(container.querySelector(".cm-content")?.textContent).toContain("안녕 세계");
    expect(viewOf(container).state.doc.toString()).toBe("안녕 세계");
  });

  it("사용자 편집만 onChange를 호출하고, 외부 value 변경은 호출하지 않는다", () => {
    const onChange = vi.fn();
    const { container, rerender } = render(<TextEditor value="a" onChange={onChange} ariaLabel="x" />);
    viewOf(container).dispatch({ changes: { from: 1, insert: "b" }, userEvent: "input.type" });
    expect(onChange).toHaveBeenCalledWith("ab");
    onChange.mockClear();
    rerender(<TextEditor value="외부" onChange={onChange} ariaLabel="x" />);
    expect(viewOf(container).state.doc.toString()).toBe("외부");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("readOnly면 편집 불가", () => {
    const { container } = render(<TextEditor value="a" readOnly ariaLabel="x" />);
    expect(viewOf(container).state.readOnly).toBe(true);
  });

  it("maxBytes 초과면 읽기 전용이 되고 onTooLarge에 바이트 수를 알린다(한글은 3바이트)", () => {
    const onTooLarge = vi.fn();
    const { container } = render(<TextEditor value="가나다" maxBytes={8} onTooLarge={onTooLarge} ariaLabel="x" messages={{ tooLarge: "너무 큼" }} />);
    expect(onTooLarge).toHaveBeenCalledWith(9);
    expect(viewOf(container).state.readOnly).toBe(true);
    expect(screen.getByRole("textbox").getAttribute("aria-description")).toBe("너무 큼");
  });

  it("Ctrl+S는 onSave를 부르고 기본 동작을 막는다", () => {
    const onSave = vi.fn();
    render(<TextEditor value="a" onSave={onSave} ariaLabel="x" />);
    const notPrevented = fireEvent.keyDown(screen.getByRole("textbox"), { key: "s", ctrlKey: true });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(false);
  });

  it("IME 조합 중에는 Ctrl+S 같은 단축키를 처리하지 않고, 조합 중 변경도 onChange로 전달한다", () => {
    const onSave = vi.fn();
    const onChange = vi.fn();
    const { container } = render(<TextEditor value="" onSave={onSave} onChange={onChange} ariaLabel="x" />);
    const content = screen.getByRole("textbox");
    const v = viewOf(container);
    fireEvent.compositionStart(content);
    fireEvent.keyDown(content, { key: "s", ctrlKey: true, isComposing: true });
    fireEvent.keyDown(content, { key: "Process", keyCode: 229, ctrlKey: true });
    expect(onSave).not.toHaveBeenCalled();
    v.dispatch({ changes: { from: 0, insert: "ㅎ" }, userEvent: "input.type.compose" });
    expect(onChange).toHaveBeenLastCalledWith("ㅎ");
    v.dispatch({ changes: { from: 0, to: 1, insert: "한" }, userEvent: "input.type.compose" });
    expect(onChange).toHaveBeenLastCalledWith("한");
    fireEvent.compositionEnd(content);
  });

  it("조합 상태 API: compositionstart/end에서 상태가 바뀔 때만 onCompositionChange를 부르고 isComposing()이 따라간다", () => {
    const onCompositionChange = vi.fn();
    const handleRef = createRef<TextEditorHandle>();
    render(<TextEditor value="" ariaLabel="x" onCompositionChange={onCompositionChange} handleRef={handleRef} />);
    const content = screen.getByRole("textbox");
    expect(handleRef.current?.isComposing()).toBe(false);
    fireEvent.compositionStart(content);
    fireEvent.compositionStart(content);
    expect(onCompositionChange.mock.calls).toEqual([[true]]);
    expect(handleRef.current?.isComposing()).toBe(true);
    fireEvent.compositionEnd(content);
    expect(onCompositionChange.mock.calls).toEqual([[true], [false]]);
    expect(handleRef.current?.isComposing()).toBe(false);
  });

  it("자동 완성·자동 괄호를 켜지 않는다(여는 괄호 입력이 짝을 만들지 않음)", () => {
    const { container } = render(<TextEditor value="" language="json" ariaLabel="x" />);
    const v = viewOf(container);
    v.dispatch({ changes: { from: 0, insert: "{" }, userEvent: "input.type" });
    expect(v.state.doc.toString()).toBe("{");
    expect(container.querySelector(".cm-tooltip-autocomplete")).toBeNull();
  });

  it("onStatus: 줄·열·글자 수, json이면 parseError", () => {
    const statuses: TextEditorStatus[] = [];
    const { container } = render(<TextEditor value={'{"a":1}'} language="json" ariaLabel="x" onStatus={(s) => statuses.push(s)} />);
    expect(statuses.at(-1)).toEqual({ line: 1, col: 1, chars: 7 });
    const v = viewOf(container);
    v.dispatch({ changes: { from: 7, insert: "\n{" }, selection: { anchor: 9 } });
    const last = statuses.at(-1)!;
    expect(last).toMatchObject({ line: 2, col: 2, chars: 9 });
    expect(last.parseError).toBeTruthy();
  });

  it("language를 바꾸면 모르는 값도 오류 없이 text로 처리한다", () => {
    const { container, rerender } = render(<TextEditor value="# 제목" language="markdown" ariaLabel="x" />);
    rerender(<TextEditor value="# 제목" language="nope" ariaLabel="x" />);
    expect(viewOf(container).state.doc.toString()).toBe("# 제목");
  });

  it("height 숫자는 px로 적용", () => {
    const { container } = render(<TextEditor value="" height={120} ariaLabel="x" />);
    expect((container.firstElementChild as HTMLElement).style.height).toBe("120px");
  });
});

describe("helpers", () => {
  it("jsonParseError", () => {
    expect(jsonParseError("")).toBeUndefined();
    expect(jsonParseError('{"a":1}')).toBeUndefined();
    expect(jsonParseError("{")).toBeTruthy();
  });
  it("resolveLanguage: 모르는 값은 빈 확장", () => {
    expect(resolveLanguage("nope")).toEqual([]);
    expect(resolveLanguage("constructor")).toEqual([]);
    expect(resolveLanguage(undefined)).toEqual([]);
    expect(resolveLanguage("json")).not.toEqual([]);
  });
});

describe("TextEditor: 줄 이동", () => {
  // happy-dom은 선택 변경 이벤트를 동기로 쏘아 포커스된 편집기에 두 번째 이동을 하면 오류가 난다. 케이스마다 새로 그린다.
  const headAfter = (line: number): number => {
    const ref = createRef<TextEditorHandle>();
    const { container, unmount } = render(<TextEditor value={"가\n나\n다"} ariaLabel="x" handleRef={ref} />);
    expect(ref.current?.goToLine(line)).toBe(true);
    const head = viewOf(container).state.selection.main.head;
    unmount();
    return head;
  };
  it("goToLine은 그 줄 처음으로 커서를 옮기고, 범위 밖은 처음·끝 줄로 맞춘다", () => {
    expect(headAfter(2)).toBe(2);
    expect(headAfter(99)).toBe(4);
    expect(headAfter(0)).toBe(0);
  });
  it("숫자가 아니면 옮기지 않고 false다", () => {
    const ref = createRef<TextEditorHandle>();
    render(<TextEditor value="가" ariaLabel="x" handleRef={ref} />);
    expect(ref.current?.goToLine(Number.NaN)).toBe(false);
  });
});

describe("TextEditor marks·goToOffset (7R.18)", () => {
  const text = "😀 가나 [[다]] 끝";
  const from = text.indexOf("[[다]]");
  it("범위를 장식으로 칠하고(UTF-16), 편집하면 글을 따라 움직인다", () => {
    const { container } = render(<TextEditor value={text} ariaLabel="x" marks={[{ from, to: from + 5, className: "m", attrs: { "data-k": "1" } }]} />);
    const mark = () => container.querySelector<HTMLElement>('[data-k="1"]');
    expect(mark()?.textContent).toBe("[[다]]");
    viewOf(container).dispatch({ changes: { from: 0, insert: "앞에서 " }, userEvent: "input.type" });
    expect(mark()?.textContent).toBe("[[다]]");
  });
  it("문서 밖·빈 범위는 버리고 새 목록을 주면 통째로 바뀐다", () => {
    const { container, rerender } = render(<TextEditor value={text} ariaLabel="x" marks={[{ from: 0, to: 0, attrs: { "data-k": "e" } }, { from: 0, to: 999, attrs: { "data-k": "o" } }]} />);
    expect(container.querySelector('[data-k="e"]')).toBeNull();
    expect(container.querySelector('[data-k="o"]')).toBeNull();
    rerender(<TextEditor value={text} ariaLabel="x" marks={[{ from: 3, to: 5, attrs: { "data-k": "n" } }]} />);
    expect(container.querySelector('[data-k="n"]')?.textContent).toBe(text.slice(3, 5));
  });
  it("goToOffset은 UTF-16 오프셋으로 커서를 옮기고 범위 밖은 끝으로 맞춘다", () => {
    const headAfter = (offset: number): number => {
      const ref = createRef<TextEditorHandle>();
      const { container, unmount } = render(<TextEditor value={text} ariaLabel="x" handleRef={ref} />);
      expect(ref.current?.goToOffset(offset)).toBe(true);
      const head = viewOf(container).state.selection.main.head;
      unmount();
      return head;
    };
    expect(headAfter(from)).toBe(from);
    expect(headAfter(9999)).toBe(text.length);
    const ref = createRef<TextEditorHandle>();
    render(<TextEditor value={text} ariaLabel="x" handleRef={ref} />);
    expect(ref.current?.goToOffset(Number.NaN)).toBe(false);
  });
});
