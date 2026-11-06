import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentEditor, type DocumentEditorHandle } from "./DocumentEditor";

afterEach(cleanup);
const doc = { id: "d1", title: "임의 문서", file: "any.md" };

describe("DocumentEditor: 변경 비교", () => {
  it("compare를 주지 않으면 [변경 비교]가 없다", () => {
    render(<DocumentEditor document={doc} value="a" />);
    expect(screen.queryByRole("button", { name: "변경 비교" })).toBeNull();
  });

  it("[변경 비교]는 기준 ↔ 편집본 비교를 열고 닫는다", () => {
    render(<DocumentEditor document={doc} value={"a\nb"} compare={{ before: "a", beforeLabel: "기준 이름" }} />);
    const button = screen.getByRole("button", { name: "변경 비교" });
    expect(button.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-pressed")).toBe("true");
    const region = screen.getByRole("region", { name: "변경 비교" });
    expect(region.textContent).toContain("기준 이름");
    fireEvent.click(screen.getAllByRole("button", { name: "닫기" })[0] as HTMLElement);
    expect(screen.queryByRole("region", { name: "변경 비교" })).toBeNull();
  });

  it("차이가 없으면 안내만 보인다", () => {
    render(<DocumentEditor document={doc} value="같음" compare={{ before: "같음" }} defaultCompareOpen />);
    expect(screen.getByText("비교할 차이가 없습니다.")).toBeTruthy();
  });
});

describe("DocumentEditor: 충돌·외부 변경 띠", () => {
  it("충돌 띠에는 [변경 비교] [최신 내용 불러오기] [내 변경으로 덮어쓰기] [내 변경 복사]가 있다", () => {
    const onReload = vi.fn();
    const onOverwrite = vi.fn();
    const onCopyMine = vi.fn();
    render(<DocumentEditor document={doc} value="mine" conflict compare={{ before: "server" }} onReload={onReload} onOverwrite={onOverwrite} onCopyMine={onCopyMine} />);
    fireEvent.click(screen.getByRole("button", { name: "최신 내용 불러오기" }));
    fireEvent.click(screen.getByRole("button", { name: "내 변경으로 덮어쓰기" }));
    fireEvent.click(screen.getByRole("button", { name: "내 변경 복사" }));
    expect([onReload, onOverwrite, onCopyMine].map((f) => f.mock.calls.length)).toEqual([1, 1, 1]);
    expect(screen.getAllByRole("button", { name: "변경 비교" }).length).toBeGreaterThan(0);
  });

  it("외부 변경(충돌 아님)은 info 띠이고 저장은 막히지 않는다", () => {
    const onSave = vi.fn();
    render(<DocumentEditor document={doc} value="mine" dirty externalChange compare={{ before: "server" }} onReload={() => {}} onSave={onSave} />);
    expect(screen.getByText(/저장하면 충돌이 납니다/)).toBeTruthy();
    const save = screen.getByRole("button", { name: "저장" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("내 변경 복사 콜백이 없으면 버튼이 없다", () => {
    render(<DocumentEditor document={doc} value="x" conflict />);
    expect(screen.queryByRole("button", { name: "내 변경 복사" })).toBeNull();
  });
});

describe("DocumentEditor: 보기 방식(제어형)·줄 이동", () => {
  it("mode를 주면 그 값이 눌림 상태이고 버튼은 onModeChange만 부른다", () => {
    const onModeChange = vi.fn();
    render(<DocumentEditor document={doc} value="x" mode="preview" onModeChange={onModeChange} />);
    expect(screen.getByRole("button", { name: "미리보기" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "편집" }));
    expect(onModeChange).toHaveBeenCalledWith("edit");
    expect(screen.getByRole("button", { name: "미리보기" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("[줄로 이동]은 입력칸을 열고, 없는 줄이면 오류를, 있는 줄이면 닫는다", () => {
    render(<DocumentEditor document={doc} value={"1\n2\n3"} defaultMode="edit" />);
    fireEvent.click(screen.getByRole("button", { name: "줄로 이동" }));
    const input = screen.getByLabelText("줄 번호") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "99" } });
    fireEvent.click(screen.getByRole("button", { name: "이동" }));
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("alert").textContent).toContain("없는 줄");
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "이동" }));
    expect(screen.queryByLabelText("줄 번호")).toBeNull();
  });

  it("핸들로도 연다(단축키용)", async () => {
    const ref = createRef<DocumentEditorHandle>();
    render(<DocumentEditor document={doc} value={"1\n2"} defaultMode="edit" handleRef={ref} />);
    expect(ref.current?.goToLine(2)).toBe(true);
    act(() => ref.current?.openGoToLine());
    expect(screen.getByLabelText("줄 번호")).toBeTruthy();
  });

  it("편집기가 보이지 않는 미리보기에서는 줄 이동이 실패한다", () => {
    const ref = createRef<DocumentEditorHandle>();
    render(<DocumentEditor document={doc} value="x" mode="preview" handleRef={ref} />);
    expect(ref.current?.goToLine(1)).toBe(false);
  });
});
