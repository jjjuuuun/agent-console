import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DefinitionPicker, sortPickItems, type DefinitionPickItem } from "./DefinitionPicker";

afterEach(cleanup);

const items: DefinitionPickItem[] = [
  { id: "c", name: "다람쥐", description: "구현" },
  { id: "a", name: "가마우지", description: "설계", usageCount: 2 },
  { id: "b", name: "나비", description: "검토" },
];

describe("sortPickItems", () => {
  it("최근 사용을 앞으로(최근 순), 나머지는 이름 순", () => {
    expect(sortPickItems(items, ["b", "c"], "").map((i) => i.id)).toEqual(["b", "c", "a"]);
  });
  it("검색어는 이름·설명·id 부분 일치", () => {
    expect(sortPickItems(items, [], "검토").map((i) => i.id)).toEqual(["b"]);
    expect(sortPickItems(items, [], "ARI").map((i) => i.id)).toEqual([]);
    expect(sortPickItems(items, [], "c").map((i) => i.id)).toEqual(["c"]);
  });
});

describe("DefinitionPicker", () => {
  it("검색창이 자동 포커스되고 '이미 N개' 칩을 보이며 Enter로 첫 항목을 고른다", () => {
    const onPick = vi.fn();
    render(<DefinitionPicker label="에이전트" items={items} onPick={onPick} />);
    const search = screen.getByRole("combobox", { name: "검색" });
    expect(document.activeElement).toBe(search);
    expect(screen.getByText("이미 2개")).toBeTruthy();
    fireEvent.keyDown(search, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: "a" })); // 이름 순 첫 항목
  });

  it("↑↓로 옮기고 최근 사용이 먼저 나온다", () => {
    const onPick = vi.fn();
    render(<DefinitionPicker label="에이전트" items={items} recentIds={["c"]} onPick={onPick} />);
    const search = screen.getByRole("combobox", { name: "검색" });
    expect(screen.getAllByRole("option")[0]!.textContent).toContain("다람쥐");
    fireEvent.keyDown(search, { key: "ArrowDown" });
    fireEvent.keyDown(search, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
  });

  it("묶음 소제목을 순서대로 그리고, 일치하는 항목이 없으면 안내한다", () => {
    const grouped: DefinitionPickItem[] = [
      { id: "1", name: "공용 하나", group: "shared" },
      { id: "2", name: "이 프로젝트 하나", group: "current" },
    ];
    render(<DefinitionPicker label="에이전트" items={grouped} groups={[{ key: "current", label: "이 프로젝트" }, { key: "shared", label: "공용" }]} onPick={() => {}} />);
    const titles = Array.from(document.querySelectorAll(".team-picker-group-title")).map((n) => n.textContent);
    expect(titles).toEqual(["이 프로젝트", "공용"]);
    fireEvent.change(screen.getByRole("combobox", { name: "검색" }), { target: { value: "없는 이름" } });
    expect(screen.getByText("일치하는 항목이 없습니다.")).toBeTruthy();
  });

  it("비활성 항목은 고를 수 없고, onCreate가 있으면 [새로 만들기…]를 보인다", () => {
    const onPick = vi.fn();
    const onCreate = vi.fn();
    render(<DefinitionPicker label="에이전트" items={[{ id: "x", name: "막힘", disabled: true }]} onPick={onPick} onCreate={onCreate} />);
    fireEvent.click(screen.getByRole("option", { name: /막힘/ }));
    expect(onPick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "새로 만들기…" }));
    expect(onCreate).toHaveBeenCalled();
  });
});
