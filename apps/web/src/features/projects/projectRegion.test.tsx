import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectRegion, type ProjectRegionProps } from "./ProjectRegion";
import { parseCollapsed, projectInitial, regionProjects, typeAheadChar, typeAheadIndex } from "./projectRegionLib";

afterEach(cleanup);

const rows = [
  { id: "a", name: "payments", folder: "/home/me/work/payments" },
  { id: "b", name: "docs-site", folder: "/home/me/work/docs-site" },
  { id: "c", name: "unset", folder: null },
];
const props = (over: Partial<ProjectRegionProps> = {}): ProjectRegionProps => ({
  projects: rows,
  currentId: "a",
  collapsed: false,
  onCollapsedChange: () => {},
  onSelect: () => {},
  onAdd: () => {},
  ...over,
});

describe("ProjectRegion", () => {
  it("펼침: 두 줄 항목(이름·경로), 현재 표시, 폴더 미지정 문구, [폴더 추가]", () => {
    const onAdd = vi.fn();
    const onSelect = vi.fn();
    render(<ProjectRegion {...props({ onAdd, onSelect })} />);
    const list = screen.getByRole("list", { name: "프로젝트 목록" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(within(list).getByRole("button", { name: /^payments/ }).getAttribute("aria-current")).toBe("true");
    expect(screen.getByText("폴더를 지정하세요")).toBeTruthy();
    fireEvent.click(within(list).getByRole("button", { name: /^docs-site/ }));
    expect(onSelect).toHaveBeenCalledWith("b");
    fireEvent.click(screen.getByRole("button", { name: "폴더 추가" }));
    expect(onAdd).toHaveBeenCalled();
  });

  it("접힘: 머리에 현재 이름이 보이고 목록은 숨고 + 버튼이 있다", () => {
    const onCollapsedChange = vi.fn();
    render(<ProjectRegion {...props({ collapsed: true, onCollapsedChange })} />);
    const toggle = screen.getByRole("button", { name: /프로젝트/, expanded: false });
    expect(toggle.textContent).toContain("payments");
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.getByRole("button", { name: "프로젝트 폴더 추가" })).toBeTruthy();
    fireEvent.click(toggle);
    expect(onCollapsedChange).toHaveBeenCalledWith(false);
  });

  it("0개: 안내와 [폴더 추가] 버튼", () => {
    render(<ProjectRegion {...props({ projects: [], currentId: null })} />);
    expect(screen.getByText("등록된 프로젝트가 없습니다")).toBeTruthy();
    expect(screen.getByRole("button", { name: "폴더 추가" })).toBeTruthy();
  });

  it("레일: 이니셜 배지 버튼이 팝오버를 연다", () => {
    const onSelect = vi.fn();
    render(<ProjectRegion {...props({ rail: true, onSelect })} />);
    const btn = screen.getByRole("button", { name: "프로젝트: payments" });
    expect(btn.textContent).toContain("P");
    fireEvent.click(btn);
    fireEvent.click(screen.getByRole("menuitemradio", { name: /docs-site/ }));
    expect(onSelect).toHaveBeenCalledWith("b");
  });
  it("레일 팝오버: 글자를 치면 이름이 그 글자로 시작하는 항목으로 포커스가 간다(type-ahead)", () => {
    render(<ProjectRegion {...props({ rail: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "프로젝트: payments" }));
    const first = screen.getByRole("menuitemradio", { name: /payments/ });
    first.focus();
    fireEvent.keyDown(first, { key: "d" });
    expect(document.activeElement).toBe(screen.getByRole("menuitemradio", { name: /docs-site/ }));
  });
});

describe("projectRegionLib", () => {
  it("보관 제외·이름 자연 정렬", () => {
    const list = regionProjects([
      { id: "1", name: "p10" },
      { id: "2", name: "p2" },
      { id: "3", name: "x", archived: true },
    ] as never);
    expect(list.map((p) => p.name)).toEqual(["p2", "p10"]);
  });
  it("이니셜·접힘 해석", () => {
    expect(projectInitial("payments")).toBe("P");
    expect(projectInitial("")).toBe("·");
    expect(parseCollapsed("1")).toBe(true);
    expect(parseCollapsed(null)).toBe(false);
  });
  it("type-ahead: 한 글자는 다음 항목부터, 여러 글자는 지금 항목부터, 한글 자모도 맞는다", () => {
    const names = ["빈 프로젝트", "새 기록", "읽기 전용", "e2e"];
    expect(typeAheadIndex(names, 0, "e")).toBe(3);
    expect(typeAheadIndex(names, 3, "e")).toBe(3);
    expect(typeAheadIndex(names, 0, "ㅇ")).toBe(2);
    expect(typeAheadIndex(names, 0, "ㅅㅐ")).toBe(1);
    expect(typeAheadIndex(names, 0, "z")).toBe(-1);
  });
  it("한글 입력기가 켜져 있으면(key=Process) 물리 키를 두벌식 자모로 바꿔 쓴다", () => {
    const base = { ctrlKey: false, metaKey: false, altKey: false, isComposing: true };
    expect(typeAheadChar({ ...base, key: "Process", code: "KeyD" })).toBe("ㅇ");
    expect(typeAheadChar({ ...base, key: "Process", code: "Enter" })).toBeUndefined();
    expect(typeAheadChar({ ...base, isComposing: false, key: "e", code: "KeyE" })).toBe("e");
    expect(typeAheadChar({ ...base, isComposing: false, key: "e", code: "KeyE", ctrlKey: true })).toBeUndefined();
  });
});
