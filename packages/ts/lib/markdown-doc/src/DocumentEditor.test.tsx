import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentEditor, type DocumentEditorHandle } from "./DocumentEditor";
import { RulesSourceBadge } from "./RulesSourceBadge";

afterEach(cleanup);

describe("DocumentEditor", () => {
  const doc = { id: "d1", title: "요구 문서", file: "req.md" };
  it("빈 상태: 문서를 고르라는 안내", () => {
    render(<DocumentEditor document={null} value="" />);
    expect(screen.getByText("문서를 고르세요")).toBeTruthy();
  });
  it("편집기와 마크다운 미리보기를 나란히 그린다", () => {
    const { container } = render(<DocumentEditor document={doc} value={"# 제목\n\n본문"} />);
    expect(container.querySelector(".cm-content")).toBeTruthy();
    const preview = screen.getByRole("region", { name: "미리보기" });
    expect(within(preview).getByRole("heading", { name: "제목" })).toBeTruthy();
  });
  it("보기 방식 전환: 편집만 → 미리보기만", () => {
    const { container } = render(<DocumentEditor document={doc} value="x" />);
    fireEvent.click(screen.getByRole("button", { name: "편집" }));
    expect(screen.queryByRole("region", { name: "미리보기" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "미리보기" }));
    expect(container.querySelector(".cm-content")).toBeNull();
    expect(screen.getByRole("region", { name: "미리보기" })).toBeTruthy();
  });
  it("미리보기는 원시 HTML을 실행하지 않는다", () => {
    const { container } = render(<DocumentEditor document={doc} value={"<img src=x onerror=alert(1)>\n\n<script>1</script>"} defaultMode="preview" />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
  it("읽기 전용: 이유를 보이고 저장을 막는다", () => {
    const onSave = vi.fn();
    const { container } = render(<DocumentEditor document={doc} value="x" readOnly readOnlyReason="폴더에 쓸 수 없습니다" dirty onSave={onSave} />);
    expect(screen.getByText("폴더에 쓸 수 없습니다")).toBeTruthy();
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect(container.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("false");
  });
  it("저장: 바뀐 내용이 있을 때만 켜지고 누르면 onSave", () => {
    const onSave = vi.fn();
    const { rerender } = render(<DocumentEditor document={doc} value="x" onSave={onSave} />);
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<DocumentEditor document={doc} value="x" dirty onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });
  it("충돌: 경고와 두 선택지를 주고 저장은 막는다", () => {
    const onReload = vi.fn();
    const onOverwrite = vi.fn();
    const onSave = vi.fn();
    render(<DocumentEditor document={doc} value="x" dirty conflict onReload={onReload} onOverwrite={onOverwrite} onSave={onSave} />);
    expect(screen.getByRole("alert").textContent).toContain("다른 곳에서 문서가 바뀌었습니다");
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "최신 내용 불러오기" }));
    fireEvent.click(screen.getByRole("button", { name: "내 변경으로 덮어쓰기" }));
    expect(onReload).toHaveBeenCalled();
    expect(onOverwrite).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });
  it("읽기 전용이면 충돌에서도 덮어쓰기가 꺼진다", () => {
    render(<DocumentEditor document={doc} value="x" readOnly conflict onOverwrite={() => undefined} />);
    expect((screen.getByRole("button", { name: "내 변경으로 덮어쓰기" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("파일 없음: 자동으로 만들지 않고 버튼만 준다", () => {
    const onCreate = vi.fn();
    const { container } = render(<DocumentEditor document={doc} value="" missing onCreateMissing={onCreate} />);
    expect(screen.getByText("req.md 파일이 사라졌습니다. 앱은 파일을 대신 만들지 않습니다.")).toBeTruthy();
    expect(container.querySelector(".cm-content")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "빈 파일로 만들기" }));
    expect(onCreate).toHaveBeenCalled();
  });
  it("점검 결과를 서버 문구 그대로 보인다", () => {
    render(<DocumentEditor document={doc} value="x" issues={[{ severity: "warning", code: "sdd.secret_suspect", message: "비밀 의심", line: 3 }]} />);
    expect(screen.getByText("sdd.secret_suspect")).toBeTruthy();
    expect(screen.getByText(/비밀 의심/)).toBeTruthy();
  });
  it("IME 조합 중에는 저장이 잠기고 안내가 뜬다", () => {
    const { container } = render(<DocumentEditor document={doc} value="x" dirty onSave={() => undefined} />);
    const content = container.querySelector(".cm-content") as HTMLElement;
    act(() => {
      fireEvent.compositionStart(content);
    });
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("입력 중에는 저장을 미룹니다")).toBeTruthy();
    act(() => {
      fireEvent.compositionEnd(content);
    });
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(false);
  });
  it("마크다운이 아닌 언어는 미리보기 없이 편집만", () => {
    render(<DocumentEditor document={doc} value="{}" language="json" />);
    expect(screen.queryByRole("region", { name: "미리보기" })).toBeNull();
    expect(screen.queryByRole("group", { name: "보기 방식" })).toBeNull();
  });
});


describe("RulesSourceBadge", () => {
  it("출처 배지: 문구 표에 없으면 원문", () => {
    const { rerender } = render(<RulesSourceBadge source="spec" messages={{ "source.spec": "스펙" }} />);
    expect(screen.getByText("출처: 스펙")).toBeTruthy();
    rerender(<RulesSourceBadge source="made-up" />);
    expect(screen.getByText("출처: made-up")).toBeTruthy();
  });
});

describe("DocumentEditor: previewHooks·이슈 타입", () => {
  const doc = { id: "d1", title: "문서", file: "a.md" };
  it("previewHooks가 미리보기에 전달된다", () => {
    render(<DocumentEditor document={doc} value="[x](wiki:p)" defaultMode="preview" previewHooks={{ urlTransform: (u) => u, renderLink: (href, children) => <b data-href={href}>{children}</b> }} />);
    expect(screen.getByText("x").getAttribute("data-href")).toBe("wiki:p");
  });
  it("line이 없는 이슈(공통 Issue 모양)도 받는다", () => {
    render(<DocumentEditor document={doc} value="x" issues={[{ severity: "warning", code: "wiki.x", message: "줄 없음" }]} />);
    expect(screen.getByText(/줄 없음/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "줄로 이동", hidden: false })?.closest("li")).toBeNull();
  });
});

describe("편집기 확장 자리 (7R.18)", () => {
  it("marks 장식·banners·statusBar·goToOffset", async () => {
    const ref: { current: DocumentEditorHandle | null } = { current: null };
    const { container, getByText } = render(
      <DocumentEditor
        document={{ id: "a", title: "문서", file: "a.md" }}
        value={"가나 [[다]] 😀 [[라]]"}
        defaultMode="edit"
        handleRef={ref}
        marks={[{ from: 3, to: 8, className: "x-link", attrs: { "data-link": "3" } }]}
        banners={<p>띠 자리</p>}
        statusBar={<span>상태 자리</span>}
      />,
    );
    expect(getByText("띠 자리")).toBeTruthy();
    expect(getByText("상태 자리")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 20));
    const mark = container.querySelector('[data-link="3"]');
    expect(mark?.textContent).toBe("[[다]]");
    expect(typeof ref.current?.goToOffset).toBe("function");
  });
});
