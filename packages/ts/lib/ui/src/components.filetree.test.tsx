import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileTree, buildFileTreeRows } from "./index";

afterEach(cleanup);

const ITEMS = [
  { path: "skills/a/SKILL.md", trailing: <span>1 KB</span> },
  { path: "skills/a/notes.md" },
  { path: "CLAUDE.md" },
];

describe("FileTree", () => {
  it("경로에서 폴더를 만들고 폴더 먼저 정렬한다", () => {
    const rows = buildFileTreeRows(ITEMS, "tree", new Set());
    expect(rows.map((r) => `${r.depth}:${r.kind}:${r.label}`)).toEqual([
      "1:folder:skills",
      "2:folder:a",
      "3:file:notes.md",
      "3:file:SKILL.md",
      "1:file:CLAUDE.md",
    ]);
  });

  it("평면 보기는 전체 경로를 한 줄씩 보인다", () => {
    render(<FileTree items={ITEMS} ariaLabel="파일" view="flat" />);
    expect(screen.getAllByRole("treeitem")).toHaveLength(3);
    expect(screen.getByText("skills/a/SKILL.md")).toBeTruthy();
  });

  it("방향키로 이동·접기·펴기, Enter로 파일을 고른다", () => {
    const onSelect = vi.fn();
    render(<FileTree items={ITEMS} ariaLabel="파일" onSelect={onSelect} />);
    const tree = screen.getByRole("tree", { name: "파일" });
    const first = screen.getAllByRole("treeitem")[0]!;
    expect(first.getAttribute("aria-expanded")).toBe("true");
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowLeft" });
    expect(screen.getAllByRole("treeitem")).toHaveLength(2); // skills 접힘 -> skills, CLAUDE.md
    fireEvent.keyDown(screen.getAllByRole("treeitem")[0]!, { key: "ArrowRight" });
    expect(screen.getAllByRole("treeitem")).toHaveLength(5);
    fireEvent.keyDown(tree.querySelectorAll<HTMLElement>("[role=treeitem]")[0]!, { key: "End" });
    const last = screen.getAllByRole("treeitem")[4]!;
    expect(document.activeElement).toBe(last);
    fireEvent.keyDown(last, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("CLAUDE.md");
  });
});
