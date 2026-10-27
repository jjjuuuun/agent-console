import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionButton, ChipRow, Dialog, Icon, Menu, PageHeader, Tabs, computeVisible, defaultIcons } from "./index";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** happy-dom은 레이아웃이 없으므로 offsetWidth·clientWidth를 흉내 낸다. */
function mockLayout(rootWidth: number, itemWidth: number) {
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockImplementation(function (this: HTMLElement) {
    return this.classList.contains("ac-tabs-more") || this.classList.contains("ac-chiprow-more") ? 60 : itemWidth;
  });
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(function (this: HTMLElement) {
    return this.classList.contains("ac-tabs-bar") || this.classList.contains("ac-chiprow") ? rootWidth : 0;
  });
}

describe("computeVisible", () => {
  it("다 들어가면 모두 보인다", () => {
    expect([...computeVisible([50, 50, 50], 4, 200, 60)]).toEqual([0, 1, 2]);
  });
  it("넘치면 더 보기 폭을 빼고 앞에서부터 채운다", () => {
    // 가용 = 150 - 60 - 4 = 86 -> 50 하나만
    expect([...computeVisible([50, 50, 50], 4, 150, 60)]).toEqual([0]);
  });
  it("우선 항목은 폭이 모자라도 보이고 원래 순서는 호출자가 유지한다", () => {
    const v = computeVisible([50, 50, 50, 50], 4, 150, 60, [3]);
    expect(v.has(3)).toBe(true);
    expect(v.size).toBe(1 + 0);
  });
  it("레이아웃을 모르면(폭 0) 모두 보인다", () => {
    expect(computeVisible([50, 50], 4, 0, 60).size).toBe(2);
  });
});

describe("Tabs 더 보기", () => {
  const tabs = ["a", "b", "c", "d", "e"].map((id) => ({ id, label: `탭 ${id}`, content: <p>내용 {id}</p> }));
  it("넘친 탭은 '더 보기' 메뉴로 가고, 메뉴에서 고르면 활성이 되어 보이는 쪽으로 승격한다", () => {
    mockLayout(260, 80);
    function Harness() {
      const [id, setId] = useState("a");
      return <Tabs tabs={tabs} activeId={id} onChange={setId} ariaLabel="탭" moreLabel="더 보기" />;
    }
    render(<Harness />);
    const more = screen.getByRole("button", { name: /더 보기/ });
    expect(more.getAttribute("aria-haspopup")).toBe("menu");
    const list = screen.getByRole("tablist");
    const hiddenIds = () => Array.from(list.querySelectorAll('[data-hidden="true"]')).map((e) => e.textContent);
    expect(hiddenIds()).toEqual(["탭 c", "탭 d", "탭 e"]);
    fireEvent.click(more);
    const menu = screen.getByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((e) => e.textContent)).toEqual(["탭 c", "탭 d", "탭 e"]);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "탭 e" }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("tab", { name: "탭 e", selected: true }).getAttribute("data-hidden")).toBeNull();
    expect(hiddenIds()).not.toContain("탭 e");
    expect(document.activeElement?.textContent).toBe("탭 e");
  });
  it("활성 탭이 뒤쪽이어도 처음부터 보이는 쪽에 있다", () => {
    mockLayout(260, 80);
    render(<Tabs tabs={tabs} activeId="e" ariaLabel="탭" />);
    expect(screen.getByRole("tab", { name: "탭 e" }).getAttribute("data-hidden")).toBeNull();
  });
  it("다 들어가면 더 보기가 없다. 레이아웃이 없어도 없다", () => {
    mockLayout(1000, 80);
    const { unmount } = render(<Tabs tabs={tabs} ariaLabel="탭" />);
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
    unmount();
    vi.restoreAllMocks();
    render(<Tabs tabs={tabs} ariaLabel="탭" />);
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
  });
  it("더 보기 메뉴는 Esc로 닫고 트리거로 포커스가 돌아간다", () => {
    mockLayout(260, 80);
    render(<Tabs tabs={tabs} ariaLabel="탭" />);
    const more = screen.getByRole("button", { name: /더 보기/ });
    fireEvent.click(more);
    fireEvent.keyDown(screen.getByRole("menuitem", { name: "탭 c" }), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(more);
  });
});

describe("ChipRow +N", () => {
  const chips = ["하나", "둘", "셋", "넷"].map((label, i) => ({ id: `c${i}`, label }));
  it("넘치면 숨기고 +N 팝오버에 숨은 칩 전체를 담는다. 칩은 title로 전체 값", () => {
    mockLayout(200, 60);
    render(<ChipRow chips={chips} ariaLabel="팀" moreLabel={(n) => `숨은 ${n}개`} />);
    const more = screen.getByRole("button", { name: "숨은 2개" });
    expect(more.textContent).toBe("+2");
    fireEvent.click(more);
    const pop = screen.getByRole("dialog", { name: "숨은 2개" });
    expect(within(pop).getAllByText(/^(셋|넷)$/)).toHaveLength(2);
    expect(screen.getAllByTitle("하나").length).toBeGreaterThan(0);
  });
  it("활성 칩은 뒤쪽이어도 보인다", () => {
    mockLayout(150, 60);
    render(<ChipRow chips={chips.map((c, i) => ({ ...c, active: i === 3 }))} ariaLabel="팀" />);
    const item = screen.getAllByText("넷")[0]!.closest(".ac-chiprow-item")!;
    expect(item.getAttribute("data-hidden")).toBeNull();
  });
  it("칩이 적으면 +N이 없다", () => {
    mockLayout(1000, 60);
    render(<ChipRow chips={chips} ariaLabel="팀" />);
    expect(screen.queryByRole("button", { name: /더 보기/ })).toBeNull();
  });
});

describe("Dialog 구조", () => {
  it("size 4종과 wide 호환, 버튼은 actions 슬롯(고정 하단)", () => {
    const { rerender } = render(
      <Dialog open title="제목" onClose={() => {}} size="xl" actions={<button type="button">적용</button>}>
        <fieldset>
          <legend>모드</legend>
          <label className="ac-choice">
            <input type="radio" name="m" />
            <span>가</span>
          </label>
        </fieldset>
      </Dialog>,
    );
    const dlg = screen.getByRole("dialog");
    expect(dlg.getAttribute("data-size")).toBe("xl");
    expect(dlg.getAttribute("data-has-actions")).toBe("true");
    expect(Array.from(dlg.children).map((c) => c.className)).toEqual(["ac-dialog-title", "ac-dialog-body", "ac-dialog-actions"]);
    expect(within(dlg.querySelector(".ac-dialog-actions") as HTMLElement).getByRole("button", { name: "적용" })).toBeTruthy();
    rerender(
      <Dialog open title="제목" onClose={() => {}} wide>
        x
      </Dialog>,
    );
    expect(screen.getByRole("dialog").getAttribute("data-size")).toBe("lg");
    expect(screen.getByRole("dialog").getAttribute("data-has-actions")).toBeNull();
  });
  it("Esc는 열린 팝오버만 닫고 다이얼로그는 닫지 않는다. 팝오버가 없으면 다이얼로그를 닫는다", () => {
    mockLayout(100, 60);
    const onClose = vi.fn();
    render(
      <Dialog open title="t" onClose={onClose}>
        <ChipRow chips={["a", "b", "c"].map((id) => ({ id, label: id }))} ariaLabel="x" />
      </Dialog>,
    );
    fireEvent.click(screen.getByRole("button", { name: /더 보기/ }));
    fireEvent.keyDown(screen.getByRole("dialog", { name: /더 보기/ }), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /더 보기/ })).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("dialog", { name: "t" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("ActionButton", () => {
  it("아이콘 전용: aria-label = 툴팁 = 라벨, 단축키가 툴팁에 붙는다", () => {
    render(<ActionButton icon="refresh" label="새로 고침" shortcut="R" />);
    const btn = screen.getByRole("button", { name: "새로 고침" });
    expect(btn.getAttribute("aria-keyshortcuts")).toBe("R");
    expect(btn.querySelector("svg")).not.toBeNull();
    expect(btn.closest(".ac-tip-host")?.querySelector(".ac-tip")?.textContent).toBe("새로 고침 (R)");
  });
  it("글자 유지 모드는 글자가 이름이고 단축키 없으면 툴팁이 없다", () => {
    render(<ActionButton icon="play" label="지금 수집" display="icon-label" />);
    expect(screen.getByRole("button", { name: "지금 수집" }).closest(".ac-tip-host")).toBeNull();
  });
  it("loading은 스피너와 aria-busy, 클릭 불가. pressed는 aria-pressed", () => {
    const onClick = vi.fn();
    render(<ActionButton icon="refresh" label="새로 고침" loading onClick={onClick} />);
    const btn = screen.getByRole("button", { name: "새로 고침" });
    expect(btn.getAttribute("aria-busy")).toBe("true");
    expect(btn.querySelector(".ac-spinner")).not.toBeNull();
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
    cleanup();
    render(<ActionButton icon="table" label="표로 보기" pressed />);
    expect(screen.getByRole("button", { name: "표로 보기" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("모르는 아이콘 이름은 라벨 첫 글자 아바타", () => {
    render(<ActionButton icon="없는-아이콘" label="가져오기" />);
    expect(screen.getByRole("button", { name: "가져오기" }).textContent).toBe("가");
  });
});

describe("PageHeader 보조 액션", () => {
  it("보조 액션은 인라인 버튼 + more 메뉴(같은 데이터)로 둘 다 렌더되고 CSS 컨테이너 쿼리가 고른다", () => {
    const onSelect = vi.fn();
    render(<PageHeader title="실행 기록" secondaryActions={[{ id: "x", label: "내보내기", icon: "play", onSelect }]} moreLabel="더 보기" actions={<button type="button">주</button>} />);
    fireEvent.click(screen.getByRole("button", { name: "내보내기" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "더 보기" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "내보내기" }));
    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("heading", { name: "실행 기록" }).getAttribute("title")).toBe("실행 기록");
  });
});

describe("Menu", () => {
  it("방향키 순환, Home/End, 첫 항목만 tab 정지점", () => {
    render(<Menu items={[{ id: "a", label: "A", onSelect() {} }, { id: "b", label: "B", disabled: true, onSelect() {} }, { id: "c", label: "C", onSelect() {} }]} />);
    const items = screen.getAllByRole("menuitem");
    expect(items.map((i) => i.tabIndex)).toEqual([0, -1, -1]);
    items[0]!.focus();
    fireEvent.keyDown(items[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[2]);
    fireEvent.keyDown(items[2]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(items[0]!, { key: "End" });
    expect(document.activeElement).toBe(items[2]);
  });
});

describe("아이콘 레지스트리 추가분(ux-overhaul 3.2)", () => {
  it("필요한 이름이 모두 있다", () => {
    for (const n of ["refresh", "close", "more", "plus", "undo", "check", "trash", "send", "stop", "panel-left-close", "panel-left-open", "filter", "columns", "table", "chevron-right", "chevron-down", "chevron-left", "expand", "play", "pencil", "pin"]) {
      expect(defaultIcons[n], n).toBeDefined();
    }
  });
  it("Icon이 그린다", () => {
    const { container } = render(<Icon name="trash" />);
    expect(container.querySelector("svg")).not.toBeNull();
    act(() => {});
  });
});


describe("QA 1회 수정", () => {
  it("더 보기 메뉴 항목은 id가 아니라 ReactNode 라벨을 그대로 그린다", () => {
    mockLayout(260, 80);
    const tabs = ["a", "b", "c", "d"].map((id) => ({ id, label: <span>이름 {id}</span>, content: null }));
    render(<Tabs tabs={tabs} ariaLabel="탭" />);
    fireEvent.click(screen.getByRole("button", { name: /더 보기/ }));
    const names = within(screen.getByRole("menu")).getAllByRole("menuitem").map((e) => e.textContent);
    expect(names).toEqual(["이름 c", "이름 d"]);
  });
  it("Dialog actions 세로 쌓기 기준은 md(content 478px)보다 작다(5.5R.30: 359)", () => {
    const css = readFileSync(join(import.meta.dirname, "tokens.css"), "utf-8");
    const m = /@container \(max-width: (\d+)px\)\s*\{\s*\.ac-dialog-actions/.exec(css);
    expect(m).not.toBeNull();
    const md = Number(/--ac-dialog-w-md:\s*(\d+)px/.exec(css)![1]) - 2;
    expect(Number(m![1])).toBeLessThan(md);
    expect(Number(m![1])).toBeGreaterThanOrEqual(359);
  });
});
