import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef, useEffect, useState } from "react";
import type { EditorSlotProps } from "./MemoryEntryEditor";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryEntryEditor, type MemoryEntryEditorHandle } from "./MemoryEntryEditor";

afterEach(cleanup);

const comp: { set?: (b: boolean) => void; change?: (v: string) => void } = {};
function Capture({ p }: { p: EditorSlotProps }) {
  useEffect(() => {
    comp.set = p.onCompositionChange;
    comp.change = p.onChange;
  });
  return <textarea aria-label="대체" value={p.value} onChange={() => undefined} />;
}

function Harness(props: { onSave: () => void; initial?: string; maxBytes?: number | null; handleRef?: React.Ref<MemoryEntryEditorHandle>; contentType?: string }) {
  const [value, setValue] = useState(props.initial ?? "");
  return (
    <MemoryEntryEditor value={value} onChange={setValue} entryKey="a/b" contentType={props.contentType ?? "text/markdown"} onSave={props.onSave}
      maxBytes={props.maxBytes ?? null} {...(props.handleRef ? { handleRef: props.handleRef } : {})} saveState="dirty" />
  );
}
const box = () => screen.getByRole("textbox", { name: "a/b 본문" });
const status = () => screen.getByRole("group", { name: "편집기 상태" });

describe("MemoryEntryEditor", () => {
  it("text-editor를 쓰고 접근 이름 '{키} 본문'을 가진다", () => {
    render(<Harness onSave={() => undefined} initial="안녕" />);
    expect(box().getAttribute("data-ac-editable")).toBe("");
    expect(document.querySelector(".cm-content")?.textContent).toContain("안녕");
  });

  it("조합 중에는 저장이 0회이고 조합이 끝나면 1회 저장된다 (수용 기준 15)", async () => {
    const onSave = vi.fn();
    const ref = createRef<MemoryEntryEditorHandle>();
    render(<Harness onSave={onSave} handleRef={ref} />);
    fireEvent.compositionStart(box());
    expect(ref.current?.isComposing()).toBe(true);
    fireEvent.keyDown(box(), { key: "s", ctrlKey: true });
    ref.current?.requestSave();
    fireEvent.keyDown(box(), { key: "s", metaKey: true });
    expect(onSave).toHaveBeenCalledTimes(0);
    expect(screen.getByText("저장 대기…")).toBeTruthy();
    fireEvent.compositionEnd(box());
    await Promise.resolve();
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.getByText("저장 안 됨")).toBeTruthy();
  });

  it("조합이 아닐 때 Ctrl+S와 requestSave는 즉시 저장한다", () => {
    const onSave = vi.fn();
    const ref = createRef<MemoryEntryEditorHandle>();
    render(<Harness onSave={onSave} handleRef={ref} />);
    fireEvent.keyDown(box(), { key: "s", ctrlKey: true });
    expect(onSave).toHaveBeenCalledTimes(1);
    ref.current?.requestSave();
    expect(onSave).toHaveBeenCalledTimes(2);
  });

  it("조합 중에는 바이트·한도 계산을 멈추고 조합이 끝나면 다시 계산한다 (수용 기준 14·15)", () => {
    function Slot() {
      const [value, setValue] = useState("");
      return (
        <MemoryEntryEditor value={value} onChange={setValue} entryKey="k" onSave={() => undefined} maxBytes={8}
          renderEditor={(p) => <Capture p={p} />} />
      );
    }
    render(<Slot />);
    expect(status().textContent).toContain("0 B / 8 B");
    act(() => comp.set?.(true));
    act(() => comp.change?.("가나다"));
    expect(status().textContent).toContain("0 B / 8 B");
    expect(status().textContent).not.toContain("한도 초과");
    act(() => comp.set?.(false));
    expect(status().textContent).toContain("9 B / 8 B");
    expect(status().textContent).toContain("한도 초과 1 B");
  });

  it("한도 초과: 상태 줄이 위험 표시(아이콘+글자)이고 저장이 막힌다 (수용 기준 14)", () => {
    const onSave = vi.fn();
    const ref = createRef<MemoryEntryEditorHandle>();
    render(<Harness onSave={onSave} maxBytes={8} initial="가나다" handleRef={ref} />);
    expect(status().textContent).toContain("9 B / 8 B");
    expect(status().textContent).toContain("한도 초과 1 B");
    expect(status().querySelector("[data-danger] .ac-mem-icon-failed")).toBeTruthy();
    fireEvent.keyDown(box(), { key: "s", ctrlKey: true });
    ref.current?.requestSave();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("한도를 모르면 막기가 없다", () => {
    const onSave = vi.fn();
    render(<Harness onSave={onSave} initial={"가".repeat(5000)} />);
    fireEvent.keyDown(box(), { key: "s", ctrlKey: true });
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(status().textContent).toContain("14.6 KiB");
  });

  it("편집기 슬롯: 다른 편집기를 꽂아도 같은 보류 규칙이 적용된다", () => {
    const onSave = vi.fn();
    const handle = createRef<MemoryEntryEditorHandle>();
    render(
      <MemoryEntryEditor value="x" onChange={() => undefined} entryKey="k" onSave={onSave} handleRef={handle}
        renderEditor={(p) => <Capture p={p} />} />,
    );
    act(() => comp.set?.(true));
    handle.current?.requestSave();
    expect(onSave).toHaveBeenCalledTimes(0);
    act(() => comp.set?.(false));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("읽기 전용이면 저장하지 않는다", () => {
    const onSave = vi.fn();
    render(<MemoryEntryEditor value="x" onChange={() => undefined} entryKey="k" onSave={onSave} readOnly />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "s", ctrlKey: true });
    expect(onSave).not.toHaveBeenCalled();
  });
});
