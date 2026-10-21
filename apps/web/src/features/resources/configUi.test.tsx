import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ResourceTypeDescriptor } from "@agent-console/contracts";
import { ConfigTab } from "./ConfigTab";
import { buildConfigUi } from "./configUi";

afterEach(cleanup);

// 임의 종류: 문자열 배열(+예시), 예시가 있는 자유 문자열, 숫자, 그냥 문자열. 이름은 스키마 모양과 무관하다.
const schema = {
  type: "object",
  properties: {
    globs: { type: "array", title: "경로 조건", items: { type: "string", examples: ["src/**/*.ts"] } },
    when: { type: "string", title: "때", examples: ["evt-a", "evt-b"] },
    limit: { type: "integer", title: "제한", description: "초 단위" },
    run: { type: "string", title: "실행" },
    mode: { type: "string", title: "모드", enum: ["x", "y"], examples: ["x"] },
  },
};
const descriptor = { id: "t-whatever", title: "임의", config_schema: schema } as unknown as ResourceTypeDescriptor;

describe("설정 폼 보강(스키마 모양으로만)", () => {
  it("문자열 배열은 태그 입력, 예시가 있는 자유 문자열은 제안+안내, 서버 ui_schema가 우선", () => {
    const ui = buildConfigUi(schema, { run: { "ui:widget": "textarea" } }) as Record<string, Record<string, unknown>>;
    expect(ui["globs"]!["ui:field"]).toBe("string-tags");
    expect((ui["globs"]!["ui:options"] as { suggestions: string[] }).suggestions).toEqual(["src/**/*.ts"]);
    expect(ui["when"]!["ui:help"]).toBe("목록에 없는 값도 사용할 수 있습니다");
    expect(ui["run"]).toEqual({ "ui:widget": "textarea" });
    expect(ui["limit"]).toBeUndefined();
    expect(ui["mode"]).toBeUndefined();
  });

  it("태그 추가(Enter)·삭제와 자유 입력, 숫자 입력이 값에 반영된다", () => {
    const onChange = vi.fn();
    render(<ConfigTab descriptor={descriptor} value={{ globs: ["a/*"] }} onChange={onChange} />);
    const add = screen.getByLabelText("항목 추가 (예: src/**/*.ts)");
    fireEvent.change(add, { target: { value: "b/**" } });
    fireEvent.keyDown(add, { key: "Enter" });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ globs: ["a/*", "b/**"] }));
    fireEvent.click(screen.getByRole("button", { name: "a/* 삭제" }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ globs: ["b/**"] }));
    fireEvent.change(screen.getByLabelText("때"), { target: { value: "목록 밖 이벤트" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ when: "목록 밖 이벤트" }));
    expect(screen.getByText("목록에 없는 값도 사용할 수 있습니다")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("제한"), { target: { value: "30" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 30 }));
  });
});
