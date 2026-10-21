import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TextDiff } from "./index";

afterEach(cleanup);

const BEFORE = "a\nb\nc\n";
const AFTER = "a\nB\nc\n";

describe("TextDiff", () => {
  it("나란히 보기: 두 편집기가 읽기 전용으로 각각의 내용을 보인다", () => {
    const { container } = render(<TextDiff before={BEFORE} after={AFTER} ariaLabel="본문 비교" mode="split" />);
    const contents = container.querySelectorAll(".cm-content");
    expect(contents).toHaveLength(2);
    expect(contents[0]?.textContent).toContain("b");
    expect(contents[1]?.textContent).toContain("B");
    expect(container.querySelector(".cm-mergeView")).not.toBeNull();
    expect(contents[0]?.getAttribute("aria-readonly")).toBe("true");
    expect(container.querySelectorAll(".cm-changedLine, .cm-deletedChunk, .cm-insertedLine").length).toBeGreaterThan(0);
  });

  it("통합 보기: 한 편집기에 삭제 조각과 추가 줄이 함께 나온다", () => {
    const { container } = render(<TextDiff before={BEFORE} after={AFTER} ariaLabel="본문 비교" mode="unified" />);
    expect(container.querySelectorAll(".cm-content")).toHaveLength(1);
    expect(container.querySelector(".cm-deletedChunk")).not.toBeNull();
    expect(container.querySelector(".cm-mergeView")).toBeNull();
  });

  it("전환 버튼이 보기 방식을 바꾸고 onModeChange로 알린다", () => {
    const onModeChange = vi.fn();
    const { container } = render(
      <TextDiff before={BEFORE} after={AFTER} ariaLabel="본문 비교" mode="split" onModeChange={onModeChange} messages={{ split: "나란히", unified: "통합" }} />,
    );
    expect(screen.getByRole("button", { name: "나란히" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "통합" }));
    expect(screen.getByRole("button", { name: "통합" }).getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector(".cm-mergeView")).toBeNull();
    expect(onModeChange).toHaveBeenLastCalledWith("unified");
  });

  it("auto: 폭을 알 수 없으면 나란히, 도구 줄은 끌 수 있다", () => {
    const { container } = render(<TextDiff before="x" after="y" ariaLabel="본문 비교" showToolbar={false} />);
    expect(container.querySelector("[data-ac-diff]")?.getAttribute("data-ac-diff")).toBe("split");
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("긴 변경 없는 구간은 접히고 안내 문구를 바꿀 수 있다", () => {
    const lines = Array.from({ length: 40 }, (_, i) => `line ${i}`);
    const after = lines.map((l, i) => (i === 39 ? "CHANGED" : l)).join("\n");
    const { container } = render(
      <TextDiff before={lines.join("\n")} after={after} ariaLabel="본문 비교" mode="unified" messages={{ unchangedLines: "변경 없음 $줄" }} />,
    );
    expect(container.querySelector(".cm-collapsedLines")?.textContent).toMatch(/변경 없음 \d+줄/);
  });

  it("접힌 구간은 버튼 역할로 탭 정지가 되고 Enter/Space로 펼쳐진다", async () => {
    const lines = Array.from({ length: 40 }, (_, i) => `line ${i}`);
    const after = lines.map((l, i) => (i === 39 ? "CHANGED" : l)).join("\n");
    const { container } = render(<TextDiff before={lines.join("\n")} after={after} ariaLabel="본문 비교" mode="unified" />);
    const fold = await waitFor(() => {
      const n = container.querySelector<HTMLElement>(".cm-collapsedLines");
      expect(n?.getAttribute("role")).toBe("button");
      return n as HTMLElement;
    });
    expect(fold.tabIndex).toBe(0);
    fireEvent.keyDown(fold, { key: "Enter" });
    expect(container.querySelector(".cm-collapsedLines")).toBeNull();
  });

  it("Space로도 접힌 구간을 펼친다", async () => {
    const lines = Array.from({ length: 40 }, (_, i) => `line ${i}`);
    const after = lines.map((l, i) => (i === 39 ? "CHANGED" : l)).join("\n");
    const { container } = render(<TextDiff before={lines.join("\n")} after={after} ariaLabel="본문 비교" mode="unified" />);
    const fold = await waitFor(() => container.querySelector(".cm-collapsedLines") as HTMLElement);
    fireEvent.keyDown(fold, { key: " " });
    expect(container.querySelector(".cm-collapsedLines")).toBeNull();
  });

  it("내용이 바뀌면 다시 그린다", () => {
    const { container, rerender } = render(<TextDiff before="x" after="y" ariaLabel="t" mode="split" />);
    rerender(<TextDiff before="x" after="zzz" ariaLabel="t" mode="split" />);
    expect(container.querySelectorAll(".cm-content")[1]?.textContent).toContain("zzz");
    expect(container.querySelectorAll(".cm-mergeView")).toHaveLength(1);
  });
});
