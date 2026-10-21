import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TidyPopover } from "./TidyPopover";
import type { TidyPopoverProps, TidyValues } from "./TidyPopover";
import { defaultMessages } from "../messages";
import { BUILTIN_DIRECTIONS } from "../logic/layout";
import { BUILTIN_EDGE_SHAPES } from "../shapes/registry";
import type { LayoutEngineDescriptor } from "../layout/types";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const engine = (id = "eng-a"): LayoutEngineDescriptor => ({
  id,
  title: `엔진 ${id}`,
  options: [
    { key: "gap", title: "간격 옵션", type: "number", default: 40, min: 8, max: 200, step: 8 },
    { key: "mode", title: "모드 옵션", type: "enum", default: "fast", choices: [{ value: "fast", title: "빠르게" }, { value: "tidy", title: "정교하게" }] },
    { key: "flag", title: "플래그 옵션", type: "boolean", default: true },
  ],
  run: async () => ({ positions: {} }),
});

const initial = (over: Partial<TidyValues> = {}): TidyValues => ({
  engineId: "eng-a",
  optionsByEngine: { "eng-a": { gap: 40, mode: "fast", flag: true } },
  direction: "lr",
  scope: "all",
  edgeShape: "",
  shapeByKind: {},
  resetRoutes: true,
  alignNodes: true,
  kinds: {},
  ...over,
});

function setup(over: Partial<TidyPopoverProps<string>> = {}) {
  const props: TidyPopoverProps<string> = {
    engines: [engine()],
    directions: BUILTIN_DIRECTIONS,
    shapes: BUILTIN_EDGE_SHAPES,
    edgeKinds: [{ id: "k1", title: "입구" }, { id: "k2", title: "답변" }],
    initial: initial(),
    nodeCount: 3,
    selectedCount: 0,
    pathCount: 2,
    compute: vi.fn(async () => "R"),
    onPreview: vi.fn(),
    onApply: vi.fn(),
    onResetAllRoutes: vi.fn(),
    onClose: vi.fn(),
    ...over,
  };
  render(<TidyPopover<string> {...props} />);
  return props;
}

describe("TidyPopover (graph-edges §4.1)", () => {
  it("엔진 옵션을 선언(number/enum/boolean)에서 그리고, 엔진이 하나면 엔진 선택 줄을 숨긴다", () => {
    setup();
    expect(screen.getByLabelText("간격 옵션")).toHaveProperty("type", "number");
    expect(screen.getByLabelText("모드 옵션").tagName).toBe("SELECT");
    expect(screen.getByLabelText("플래그 옵션")).toHaveProperty("type", "checkbox");
    expect(screen.queryByLabelText("엔진")).toBeNull();
  });
  it("엔진이 둘 이상이면 선택 줄이 나타나고 바꾸면 그 엔진의 옵션이 그려진다", () => {
    const b: LayoutEngineDescriptor = { ...engine("eng-b"), options: [{ key: "only-b", title: "비 전용", type: "boolean", default: false }] };
    setup({ engines: [engine(), b], initial: initial({ optionsByEngine: { "eng-a": { gap: 40, mode: "fast", flag: true }, "eng-b": { "only-b": false } } }) });
    fireEvent.change(screen.getByLabelText("엔진"), { target: { value: "eng-b" } });
    expect(screen.getByLabelText("비 전용")).toBeTruthy();
    expect(screen.queryByLabelText("간격 옵션")).toBeNull();
  });
  it("방향·모양·종류는 주어진 목록에서 그린다", () => {
    setup({ directions: { zig: { in: "left", out: "right" }, zag: { in: "top", out: "bottom" } }, initial: initial({ direction: "zig" }) });
    expect(screen.getAllByRole("radio").filter((r) => r.tagName === "BUTTON")).toHaveLength(2);
    expect(screen.getAllByRole("option", { name: "직선" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("group", { name: "배치에 쓸 연결" }).textContent).toContain("입구");
    expect(screen.getByRole("group", { name: "배치에 쓸 연결" }).textContent).toContain("답변");
  });
  it("미리보기는 onApply를 부르지 않고 다시 누르면 해제한다", async () => {
    const p = setup();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "미리보기" })));
    expect(p.onPreview).toHaveBeenLastCalledWith("R");
    expect(p.onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "미리보기 해제" }));
    expect(p.onPreview).toHaveBeenLastCalledWith(null);
  });
  it("적용은 onApply를 한 번, 값과 함께 부른다(미리보기 결과 재사용)", async () => {
    const p = setup();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "미리보기" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
    expect(p.onApply).toHaveBeenCalledTimes(1);
    expect(p.onApply).toHaveBeenCalledWith("R", expect.objectContaining({ direction: "lr", resetRoutes: true }));
    expect(p.compute).toHaveBeenCalledTimes(1);
  });
  it("값을 바꾸면 미리보기를 해제하고 바뀐 값으로 다시 계산한다", async () => {
    const p = setup();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "미리보기" })));
    fireEvent.click(screen.getByRole("radio", { name: "아래" }));
    expect(p.onPreview).toHaveBeenLastCalledWith(null);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
    expect(p.compute).toHaveBeenCalledTimes(2);
    expect((p.onApply as ReturnType<typeof vi.fn>).mock.calls[0]![1].direction).toBe("tb");
  });
  it("Enter는 적용, 값 변경은 onValuesChange로 알린다", async () => {
    const onValuesChange = vi.fn();
    const p = setup({ onValuesChange });
    fireEvent.change(screen.getByLabelText("간격 옵션"), { target: { value: "64" } });
    expect(onValuesChange).toHaveBeenLastCalledWith(expect.objectContaining({ optionsByEngine: { "eng-a": expect.objectContaining({ gap: 64 }) } }));
    await act(async () => fireEvent.keyDown(screen.getByLabelText("간격 옵션"), { key: "Enter" }));
    expect(p.onApply).toHaveBeenCalledTimes(1);
  });
  it("노드가 둘 미만이면 적용·미리보기가 비활성이고 이유를 보인다", () => {
    setup({ nodeCount: 1 });
    expect(screen.getByRole("button", { name: "적용" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "미리보기" })).toHaveProperty("disabled", true);
    expect(screen.getAllByText("정리할 노드가 둘 이상 필요합니다").length).toBeGreaterThan(0);
  });
  it("선택 범위는 선택 노드가 둘 미만이면 막힌다", () => {
    setup({ selectedCount: 1, initial: initial({ scope: "selected" }) });
    expect(screen.getByRole("button", { name: "적용" })).toHaveProperty("disabled", true);
  });
  it("계산 중에는 적용 버튼이 aria-busy이고 Esc로 중단하면 아무것도 바꾸지 않는다", async () => {
    let signal: AbortSignal | undefined;
    const compute = vi.fn((_v: TidyValues, s: AbortSignal) => {
      signal = s;
      return new Promise<string>((_, reject) => s.addEventListener("abort", () => reject(Object.assign(new Error("a"), { name: "AbortError" }))));
    });
    const onRunningChange = vi.fn();
    const p = setup({ compute, onRunningChange });
    fireEvent.click(screen.getByRole("button", { name: "적용" }));
    expect(screen.getByRole("button", { name: "정리 계산 중…" }).getAttribute("aria-busy")).toBe("true");
    expect(onRunningChange).toHaveBeenLastCalledWith(true);
    await act(async () => fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" }));
    expect(signal?.aborted).toBe(true);
    expect(p.onApply).not.toHaveBeenCalled();
    expect(p.onClose).not.toHaveBeenCalled(); // 계산만 취소하고 팝오버는 남는다
    expect(onRunningChange).toHaveBeenLastCalledWith(false);
    expect(screen.queryByRole("alert")).toBeNull();
    await act(async () => fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" }));
    expect(p.onClose).toHaveBeenCalledTimes(1);
  });
  it("실패하면 오류 줄과 다시 시도, 데이터는 바뀌지 않는다", async () => {
    const compute = vi.fn().mockRejectedValueOnce(new Error("엔진을 불러오지 못했습니다")).mockResolvedValueOnce("R");
    const p = setup({ compute });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "적용" })));
    expect(screen.getByRole("alert").textContent).toContain("정리하지 못했습니다: 엔진을 불러오지 못했습니다");
    expect(p.onApply).not.toHaveBeenCalled();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "다시 시도" })));
    expect(p.onApply).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("시간 제한(기본 10초)을 넘으면 중단하고 시간 초과를 알린다", async () => {
    vi.useFakeTimers();
    const compute = vi.fn((_v: TidyValues, s: AbortSignal) => new Promise<string>((_, reject) => s.addEventListener("abort", () => reject(Object.assign(new Error("a"), { name: "AbortError" })))));
    const p = setup({ compute });
    fireEvent.click(screen.getByRole("button", { name: "적용" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_999);
    });
    expect(screen.queryByRole("alert")).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2);
    });
    expect(screen.getByRole("alert").textContent).toContain("시간이 초과되었습니다(10초)");
    expect(p.onApply).not.toHaveBeenCalled();
  });
  it("[모든 연결선 경로 초기화]는 확인 뒤에만 부른다(취소하면 부르지 않음)", () => {
    const p = setup();
    fireEvent.click(screen.getByRole("button", { name: "모든 연결선 경로 초기화" }));
    expect(screen.getByRole("alertdialog").textContent).toContain("연결선 2개");
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "취소" }));
    expect(p.onResetAllRoutes).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "모든 연결선 경로 초기화" }));
    fireEvent.click(screen.getByRole("button", { name: "초기화" }));
    expect(p.onResetAllRoutes).toHaveBeenCalledTimes(1);
  });
  it("초기화할 경로가 없으면 확인 없이 안내만 한다", () => {
    const p = setup({ pathCount: 0 });
    fireEvent.click(screen.getByRole("button", { name: "모든 연결선 경로 초기화" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(p.onResetAllRoutes).not.toHaveBeenCalled();
  });
  it("메시지를 prop으로 바꿀 수 있다", () => {
    setup({ messages: { ...defaultMessages, tidyApply: "Apply" } });
    expect(screen.getByRole("button", { name: "Apply" })).toBeTruthy();
  });

  describe("엔진이 권장 연결선 모양을 선언했을 때(4R.20)", () => {
    const withOption = (def = true): LayoutEngineDescriptor => ({ ...engine(), edgeShapeOption: { shapeId: "auto", default: def } });
    it("선언이 없으면 '연결선도 자동 경로로' 체크가 없다", () => {
      setup();
      expect(screen.queryByRole("checkbox", { name: "연결선도 자동 경로로" })).toBeNull();
    });
    it("선언이 있으면 체크가 나타나고, 켜면 기본 모양이 그 모양이 되며 끄면 상속으로 돌아간다", () => {
      setup({ engines: [withOption()] });
      const box = screen.getByRole("checkbox", { name: "연결선도 자동 경로로" }) as HTMLInputElement;
      const select = screen.getByLabelText("기본 모양") as HTMLSelectElement;
      expect(box.checked).toBe(false);
      fireEvent.click(box);
      expect(select.value).toBe("auto");
      expect(box.checked).toBe(true);
      fireEvent.click(box);
      expect(select.value).toBe("");
    });
    it("기본 모양 선택과 체크가 서로 따라간다(체크한 모양이 아닌 값을 고르면 체크가 풀린다)", () => {
      setup({ engines: [withOption()], initial: initial({ edgeShape: "auto" }) });
      const box = screen.getByRole("checkbox", { name: "연결선도 자동 경로로" }) as HTMLInputElement;
      expect(box.checked).toBe(true);
      fireEvent.change(screen.getByLabelText("기본 모양"), { target: { value: "bezier" } });
      expect(box.checked).toBe(false);
    });
    it("적용하면 체크한 모양이 onApply의 값에 들어간다", async () => {
      const p = setup({ engines: [withOption()], initial: initial({ edgeShape: "auto" }) });
      fireEvent.click(screen.getByRole("button", { name: "적용" }));
      await act(async () => {});
      expect(p.onApply).toHaveBeenCalledTimes(1);
      expect((p.onApply as ReturnType<typeof vi.fn>).mock.calls[0]![1]).toMatchObject({ edgeShape: "auto" });
    });
    it("선언한 모양이 모양 목록에 없으면 체크를 숨긴다", () => {
      setup({ engines: [{ ...engine(), edgeShapeOption: { shapeId: "no-such", default: true } }] });
      expect(screen.queryByRole("checkbox", { name: "연결선도 자동 경로로" })).toBeNull();
    });
    it("선언의 title이 있으면 그 문구를 쓴다", () => {
      setup({ engines: [{ ...engine(), edgeShapeOption: { shapeId: "auto", default: true, title: "Route around nodes" } }] });
      expect(screen.getByRole("checkbox", { name: "Route around nodes" })).toBeTruthy();
    });
  });
});
