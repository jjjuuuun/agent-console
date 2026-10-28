import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ResourceTypeDescriptor } from "@agent-console/contracts";
import { ConfigWidgetsProvider } from "../../app/ConfigWidgets";
import { ConfigTab } from "./ConfigTab";

afterEach(cleanup);

// 메모리와 무관한 임의 종류: enum 배열 + 이름 있는 위젯 필드. QA 5.7R.19 회귀 확인.
const schema = {
  type: "object",
  properties: {
    picks: { type: "array", title: "고르기", items: { type: "string", enum: ["aa", "bb", "cc"] } },
    kind: { type: "string", title: "종류 필드", "x-ui": { widget: "w-test" } },
  },
};
const descriptor = { id: "t-other", title: "임의", config_schema: schema } as unknown as ResourceTypeDescriptor;

describe("enum 배열 체크박스·위젯 표 주입(다른 종류 회귀)", () => {
  it("공급자가 없어도 enum 배열은 체크박스로 그려지고 토글이 값에 반영된다. 모르는 위젯 이름은 기본 입력", () => {
    const onChange = vi.fn();
    render(<ConfigTab descriptor={descriptor} value={{ picks: ["aa"] }} onChange={onChange} />);
    const aa = screen.getByRole("checkbox", { name: "aa" }) as HTMLInputElement;
    expect(aa.checked).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "cc" }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ picks: expect.arrayContaining(["aa", "cc"]) }));
    expect(screen.getByLabelText("종류 필드")).toBeTruthy();
  });

  it("주입한 위젯 표의 이름만 위젯으로 그려진다(표를 바꾸면 결과가 바뀐다)", () => {
    const W = () => <div data-testid="injected">주입 위젯</div>;
    render(
      <ConfigWidgetsProvider widgets={{ "w-test": W }}>
        <ConfigTab descriptor={descriptor} value={{}} onChange={() => undefined} />
      </ConfigWidgetsProvider>,
    );
    expect(screen.getByTestId("injected")).toBeTruthy();
  });
});
