import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GroupHeader, ListPane, ListViewMenu, type ListPaneGroup, type ListViewOption } from "./index";

afterEach(cleanup);

interface Row { id: string; name: string }
const a: Row = { id: "a", name: "가" };
const b: Row = { id: "b", name: "나" };
const c: Row = { id: "c", name: "다" };
const msgs = { listLabel: "목록" };

function groups(collapsed: string[] = []): ListPaneGroup<Row>[] {
  const mk = (key: string, depth: number, items: Row[]): ListPaneGroup<Row> => ({ key, label: key.split("/").pop(), title: key, count: items.length, depth, collapsed: collapsed.includes(key), items });
  return [mk("개발팀", 0, [a, b]), mk("개발팀/백엔드", 1, [b]), mk("기타", 0, [c])];
}

function Harness({ initial = [] as string[], onSelect = () => {} }: { initial?: string[]; onSelect?: (id: string) => void }) {
  const [collapsed, setCollapsed] = useState(initial);
  return (
    <ListPane
      items={[]}
      groups={groups(collapsed)}
      onToggleGroup={(key, next) => setCollapsed((cur) => (next ? [...cur, key] : cur.filter((k) => k !== key)))}
      selectedId="b"
      onSelect={(id) => onSelect(id)}
      renderItem={(r) => r.name}
      messages={msgs}
    />
  );
}

describe("GroupHeader", () => {
  it("button aria-expanded, 이름·개수, 깊이만큼 들여쓰기(최대 3)", () => {
    const onToggle = vi.fn();
    render(<GroupHeader label="백엔드" title="개발팀/백엔드" count={1} depth={9} collapsed={false} onToggle={onToggle} />);
    const btn = screen.getByRole("button", { name: /백엔드/ });
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(btn.getAttribute("title")).toBe("개발팀/백엔드");
    expect(btn.textContent).toContain("(1)");
    expect(btn.style.paddingLeft).toContain("3 * 12px");
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalled();
  });
});

describe("ListPane groups", () => {
  it("머리·group·항목 구조, 선택은 모든 사본에 켜짐", () => {
    render(<Harness />);
    expect(screen.getByRole("listbox", { name: "목록" })).toBeTruthy();
    const heads = screen.getAllByRole("button");
    expect(heads.map((h) => h.getAttribute("aria-expanded"))).toEqual(["true", "true", "true"]);
    const selected = screen.getAllByRole("option").filter((o) => o.getAttribute("aria-selected") === "true");
    expect(selected).toHaveLength(2);
    const group = screen.getAllByRole("group")[0]!;
    expect(group.getAttribute("aria-labelledby")).toBe(heads[0]!.id);
    expect(heads[0]!.getAttribute("aria-controls")).toBe(group.id);
  });
  it("접힌 묶음은 항목을 그리지 않고 aria-controls도 없다", () => {
    render(<Harness initial={["개발팀"]} />);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["나", "다"]);
    expect(screen.getByRole("button", { name: /개발팀 \(2\)/ }).getAttribute("aria-controls")).toBeNull();
  });
  it("머리: ←로 접고 →로 펴고 Enter로 토글, 포커스 유지", () => {
    render(<Harness />);
    const head = screen.getByRole("button", { name: /^개발팀 \(2\)/ });
    head.focus();
    fireEvent.keyDown(head, { key: "ArrowLeft" });
    expect(head.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(head);
    fireEvent.keyDown(head, { key: "ArrowRight" });
    expect(head.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(head);
    expect(head.getAttribute("aria-expanded")).toBe("false");
  });
  it("↑↓가 머리와 항목을 순서대로 오가고 Enter는 항목만 선택", () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={(id) => onSelect(id)} />);
    const head = screen.getByRole("button", { name: /^개발팀 \(2\)/ });
    head.focus();
    fireEvent.keyDown(head, { key: "ArrowDown" });
    expect(document.activeElement?.getAttribute("role")).toBe("option");
    expect(document.activeElement?.textContent).toBe("가");
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("a");
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement?.textContent).toBe("다");
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement).toBe(head);
  });
  it("Tab 정지점은 하나(roving)", () => {
    render(<Harness />);
    const stops = [...screen.getAllByRole("button"), ...screen.getAllByRole("option")].filter((e) => (e as HTMLElement).tabIndex === 0);
    expect(stops).toHaveLength(1);
  });
  it("groups가 비면 빈 슬롯", () => {
    render(<ListPane items={[a]} groups={[]} onSelect={() => {}} renderItem={() => null} empty={<p>비었음</p>} messages={msgs} />);
    expect(screen.getByText("비었음")).toBeTruthy();
  });
});

const groupOptions: ListViewOption[] = [
  { id: "", label: "묶지 않음" },
  { id: "folder", label: "폴더" },
  { id: "role", label: "역할", disabled: true, reason: "값이 모두 달라 묶을 수 없습니다" },
  { id: "attr", label: "속성 키…", input: { label: "속성 키", value: "", onChange: () => {}, suggestions: ["team_tag"] } },
];
const sortOptions: ListViewOption[] = [{ id: "name", label: "이름" }, { id: "usage", label: "사용 많은 순" }];
const menuMessages = { menuLabel: "보기", groupTitle: "묶는 기준", sortTitle: "정렬", collapseAll: "모두 접기", expandAll: "모두 펼치기" };

function MenuHarness(p: { onGroup?: (id: string) => void; onSort?: (id: string) => void; groupBy?: string; anyCollapsed?: boolean; onCollapseAll?: () => void; onExpandAll?: () => void }) {
  return (
    <ListViewMenu
      summary="폴더별 · 이름순"
      groupOptions={groupOptions}
      groupBy={p.groupBy ?? "folder"}
      onGroupByChange={p.onGroup ?? (() => {})}
      sortOptions={sortOptions}
      sort="name"
      onSortChange={p.onSort ?? (() => {})}
      onCollapseAll={p.onCollapseAll}
      onExpandAll={p.onExpandAll}
      anyCollapsed={p.anyCollapsed}
      messages={menuMessages}
    />
  );
}

describe("ListViewMenu", () => {
  it("트리거 글자, 열면 menu + menuitemradio, 선택 표시", () => {
    render(<MenuHarness />);
    const trigger = screen.getByRole("button", { name: /폴더별 · 이름순/ });
    expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(trigger);
    expect(screen.getByRole("menu", { name: "보기" })).toBeTruthy();
    const radios = screen.getAllByRole("menuitemradio");
    expect(radios.filter((r) => r.getAttribute("aria-checked") === "true").map((r) => r.textContent)).toEqual(["폴더", "이름"]);
  });
  it("선택은 즉시 콜백, 메뉴는 열린 채. 비활성은 aria-disabled + 사유, 콜백 없음", () => {
    const onGroup = vi.fn();
    const onSort = vi.fn();
    render(<MenuHarness onGroup={onGroup} onSort={onSort} />);
    fireEvent.click(screen.getByRole("button", { name: /폴더별/ }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "묶지 않음" }));
    expect(onGroup).toHaveBeenLastCalledWith("");
    fireEvent.click(screen.getByRole("menuitemradio", { name: "사용 많은 순" }));
    expect(onSort).toHaveBeenLastCalledWith("usage");
    const role = screen.getByRole("menuitemradio", { name: /역할/ });
    expect(role.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("값이 모두 달라 묶을 수 없습니다")).toBeTruthy();
    fireEvent.click(role);
    expect(onGroup).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("menu")).toBeTruthy();
  });
  it("↑↓로 항목 이동, Esc로 닫으면 트리거로 포커스 복귀", () => {
    render(<MenuHarness />);
    const trigger = screen.getByRole("button", { name: /폴더별/ });
    fireEvent.click(trigger);
    const folder = screen.getByRole("menuitemradio", { name: "폴더" });
    folder.focus();
    fireEvent.keyDown(folder, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("역할");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(folder);
    fireEvent.keyDown(folder, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("선택된 항목의 입력(속성 키)과 자동완성", () => {
    render(<MenuHarness groupBy="attr" />);
    fireEvent.click(screen.getByRole("button", { name: /폴더별/ }));
    const input = screen.getByLabelText("속성 키") as HTMLInputElement;
    expect(input.getAttribute("list")).toBeTruthy();
    expect(document.querySelector("datalist option")?.getAttribute("value")).toBe("team_tag");
  });
  it("모두 접기/펼치기: 옆 단추는 접힘 여부에 따라 바뀌고 메뉴에도 있다", () => {
    const onCollapseAll = vi.fn();
    const onExpandAll = vi.fn();
    const { rerender } = render(<MenuHarness onCollapseAll={onCollapseAll} onExpandAll={onExpandAll} />);
    fireEvent.click(screen.getByRole("button", { name: "모두 접기" }));
    expect(onCollapseAll).toHaveBeenCalledTimes(1);
    rerender(<MenuHarness onCollapseAll={onCollapseAll} onExpandAll={onExpandAll} anyCollapsed />);
    fireEvent.click(screen.getByRole("button", { name: "모두 펼치기" }));
    expect(onExpandAll).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /폴더별/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "모두 접기" }));
    expect(onCollapseAll).toHaveBeenCalledTimes(2);
  });
  it("접기 콜백이 없으면 접기 단추가 없다", () => {
    render(<MenuHarness />);
    expect(screen.queryByRole("button", { name: "모두 접기" })).toBeNull();
  });
});
