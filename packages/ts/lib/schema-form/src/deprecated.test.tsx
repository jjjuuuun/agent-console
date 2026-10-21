import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SchemaForm } from "./index";
import { applyDeprecated } from "./deprecated";
import { DEFAULT_MESSAGES } from "./messages";

afterEach(cleanup);

// 도메인과 무관한 임의 스키마·필드 이름.
const schema = {
  type: "object",
  required: ["old"],
  properties: {
    keep: { type: "string", title: "유지 값" },
    old: { type: "string", title: "옛 값", description: "설명 문장", deprecated: true },
    group: { $ref: "#/$defs/Group" },
  },
  $defs: {
    Group: {
      type: "object",
      title: "묶음",
      properties: {
        inner: { type: "string", title: "안쪽 값" },
        innerOld: { type: "string", title: "안쪽 옛 값", deprecated: true },
      },
    },
  },
};

describe("deprecated 일반 규칙", () => {
  it("값이 없는 폐기 예정 필드는 그리지 않고 안내 문구도 두지 않는다(참조 안쪽 포함)", () => {
    render(<SchemaForm schema={schema} value={{ keep: "a" }} />);
    expect(screen.getByLabelText("유지 값")).toBeTruthy();
    expect(screen.getByLabelText("안쪽 값")).toBeTruthy();
    expect(screen.queryByLabelText(/옛 값/)).toBeNull();
    expect(screen.queryByText(DEFAULT_MESSAGES.deprecatedNote)).toBeNull();
    expect(screen.queryByText(/숨김/)).toBeNull();
  });

  it("값이 있으면 그리고 칩 문구와 안내를 달며, 값은 계속 편집할 수 있다", () => {
    const onChange = vi.fn();
    render(<SchemaForm schema={schema} value={{ old: "남은 값", group: { innerOld: "안쪽" } }} onChange={onChange} />);
    const field = screen.getByLabelText(new RegExp(`^옛 값 · ${DEFAULT_MESSAGES.deprecatedChip}`));
    expect((field as HTMLInputElement).value).toBe("남은 값");
    expect(screen.getAllByText(new RegExp(DEFAULT_MESSAGES.deprecatedNote)).length).toBe(2);
    expect(screen.getByLabelText(new RegExp(`안쪽 옛 값 · ${DEFAULT_MESSAGES.deprecatedChip}`))).toBeTruthy();
    fireEvent.change(field, { target: { value: "바뀜" } });
    expect(onChange).toHaveBeenCalled();
    expect((onChange.mock.calls.at(-1)?.[0] as { old: string }).old).toBe("바뀜");
  });

  it("폐기 예정 필드가 없는 스키마는 그대로 돌려준다", () => {
    const plain = { type: "object", properties: { a: { type: "string" } } };
    const out = applyDeprecated(plain, {}, DEFAULT_MESSAGES);
    expect(out.schema).toBe(plain);
    expect(out.ui).toBeUndefined();
  });

  it("required에서도 빠진다", () => {
    const out = applyDeprecated(schema, {}, DEFAULT_MESSAGES);
    expect((out.schema as { required: string[] }).required).toEqual([]);
  });
});
