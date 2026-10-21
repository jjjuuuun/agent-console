import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfirmDialog, Dialog, EmptyState, Gauge, ProvenanceBadge, Sidebar, Tabs, ToastProvider, formatBadgeCount, groupSidebarItems, useToast, type SidebarItem } from "./index";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const messages = { navLabel: "주 메뉴", collapse: "접기", expand: "펼치기" };
const items: SidebarItem[] = [
  { id: "a", label: "가", href: "#/a", badge: { count: 120, label: "응답 대기 120건" } },
  { id: "b", label: "나" },
  { id: "c", label: "다", position: "bottom", icon: <svg data-testid="c-icon" /> },
];

describe("Sidebar", () => {
  it("루트는 aside(complementary) landmark이고 regionLabel이 이름이 된다", () => {
    const { container } = render(<Sidebar items={items} onNavigate={() => {}} collapsed={false} onCollapsedChange={() => {}} messages={{ ...messages, regionLabel: "사이드바" }} />);
    expect(container.firstElementChild?.tagName).toBe("ASIDE");
    expect(screen.getByRole("complementary", { name: "사이드바" })).toBeTruthy();
  });
  it("항목 데이터로 그리고 활성 항목에 aria-current, 배지는 의미 라벨과 99+", () => {
    render(<Sidebar items={items} activeId="b" onNavigate={() => {}} collapsed={false} onCollapsedChange={() => {}} messages={messages} />);
    expect(screen.getByRole("navigation", { name: "주 메뉴" })).toBeTruthy();
    expect(screen.getByText("나").closest("[aria-current]")?.getAttribute("aria-current")).toBe("page");
    expect(screen.getByLabelText("응답 대기 120건").textContent).toBe("99+");
    expect(formatBadgeCount(5)).toBe("5");
  });
  it("Tab 정지점은 활성 항목 하나(주 메뉴)이고 방향키로 이동한다. 도구줄은 별도 정지점", () => {
    render(<Sidebar items={items} activeId="b" onNavigate={() => {}} collapsed={false} onCollapsedChange={() => {}} messages={messages} />);
    const nav = within(screen.getByRole("navigation", { name: "주 메뉴" }));
    const stops = nav.getAllByRole("button").concat(nav.queryAllByRole("link")).filter((el) => el.tabIndex === 0);
    expect(stops.map((e) => e.textContent)).toEqual(["나"]);
    const b = screen.getByText("나").closest("button")!;
    b.focus();
    fireEvent.keyDown(b, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toContain("가");
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement?.textContent).toBe("나");
  });
  it("position:bottom 항목은 하단 도구줄에 아이콘만 그려지고 이름은 aria-label·툴팁이다", () => {
    const onNavigate = vi.fn();
    render(<Sidebar items={items} onNavigate={onNavigate} collapsed={false} onCollapsedChange={() => {}} messages={{ ...messages, tools: "도구" }} />);
    const tools = within(screen.getByRole("group", { name: "도구" }));
    const tool = tools.getByRole("button", { name: "다" });
    expect(tool.textContent).toBe("");
    expect(tool.getAttribute("title")).toBe("다");
    expect(within(screen.getByRole("navigation", { name: "주 메뉴" })).queryByText("다")).toBeNull();
    fireEvent.click(tool);
    expect(onNavigate).toHaveBeenCalledWith("c");
  });
  it("묶음: 제목은 목록 이름이 되고, 항목이 없는 묶음은 그리지 않으며, 모르는 묶음의 항목은 제목 없이 맨 앞에 둔다", () => {
    const grouped: SidebarItem[] = [
      { id: "x", label: "엑스", group: "g2" },
      { id: "y", label: "와이", group: "g1" },
      { id: "z", label: "제트", group: "없는묶음" },
    ];
    const groups = [{ id: "g1", label: "첫째" }, { id: "g2", label: "둘째" }, { id: "g3", label: "빈 묶음" }];
    expect(groupSidebarItems(grouped, groups).map((s) => [s.label, s.items.map((i) => i.id)])).toEqual([[undefined, ["z"]], ["첫째", ["y"]], ["둘째", ["x"]]]);
    render(<Sidebar items={grouped} groups={groups} onNavigate={() => {}} collapsed={false} onCollapsedChange={() => {}} messages={messages} />);
    expect(screen.getByRole("list", { name: "첫째" })).toBeTruthy();
    expect(screen.getByRole("list", { name: "둘째" })).toBeTruthy();
    expect(screen.queryByText("빈 묶음")).toBeNull();
  });
  it("접기 버튼은 이름 하나(toggle)이고 aria-expanded가 상태, 탭 순서에 들어간다", () => {
    const onCollapsedChange = vi.fn();
    const { rerender } = render(<Sidebar items={items} onNavigate={() => {}} collapsed={false} onCollapsedChange={onCollapsedChange} messages={{ ...messages, toggle: "사이드바 접기/펴기", toggleTitle: "사이드바 (Ctrl+Shift+B)" }} />);
    const btn = screen.getByRole("button", { name: "사이드바 접기/펴기" });
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(btn.tabIndex).toBe(0);
    expect(btn.getAttribute("title")).toBe("사이드바 (Ctrl+Shift+B)");
    fireEvent.click(btn);
    expect(onCollapsedChange).toHaveBeenCalledWith(true);
    rerender(<Sidebar items={items} onNavigate={() => {}} collapsed onCollapsedChange={onCollapsedChange} messages={{ ...messages, toggle: "사이드바 접기/펴기" }} />);
    expect(screen.getByRole("button", { name: "사이드바 접기/펴기" }).getAttribute("aria-expanded")).toBe("false");
  });
  it("클릭 시 onNavigate(id), 수식키 클릭은 브라우저에 맡긴다", () => {
    const onNavigate = vi.fn();
    render(<Sidebar items={items} onNavigate={onNavigate} collapsed={false} onCollapsedChange={() => {}} messages={messages} />);
    fireEvent.click(screen.getByText("나"));
    expect(onNavigate).toHaveBeenCalledWith("b");
    fireEvent.click(screen.getByText("가").closest("a")!, { ctrlKey: true });
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
  it("접힘 토글과 접힘 시 툴팁", () => {
    const onCollapsedChange = vi.fn();
    const { container } = render(<Sidebar items={items} collapsed onCollapsedChange={onCollapsedChange} onNavigate={() => {}} messages={messages} />);
    expect(container.querySelector(".ac-sidebar")?.getAttribute("data-collapsed")).toBe("true");
    expect(container.querySelectorAll(".ac-sidebar-tip").length).toBe(2);
    fireEvent.click(screen.getByRole("button", { name: "펼치기" }));
    expect(onCollapsedChange).toHaveBeenCalledWith(false);
  });
});

describe("Dialog / ConfirmDialog", () => {
  it("role=dialog, Esc로 닫기, 포커스 복귀", () => {
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>열기</button>
          <Dialog open={open} title="제목" onClose={() => setOpen(false)}>
            <button>안</button>
          </Dialog>
        </>
      );
    }
    render(<Host />);
    const trigger = screen.getByText("열기");
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "제목" })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("danger 확인창은 기본 포커스가 취소 버튼, 문구는 props", () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog open danger title="삭제?" confirmLabel="삭제" cancelLabel="취소" onConfirm={onConfirm} onCancel={() => {}} />);
    expect(document.activeElement?.textContent).toBe("취소");
    fireEvent.click(screen.getByText("삭제"));
    expect(onConfirm).toHaveBeenCalled();
  });
});

describe("Toast", () => {
  function Pusher({ onUndo }: { onUndo: () => void }) {
    const toast = useToast();
    return <button onClick={() => toast({ text: "저장됨", tone: "danger", action: { label: "되돌리기", onClick: onUndo } })}>푸시</button>;
  }
  it("오류는 assertive, 액션 버튼은 한 번 누르면 닫힌다, 시간이 지나면 사라진다", () => {
    vi.useFakeTimers();
    const onUndo = vi.fn();
    render(
      <ToastProvider regionLabel="알림">
        <Pusher onUndo={onUndo} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("푸시"));
    expect(screen.getByRole("region", { name: "알림" })).toBeTruthy();
    expect(screen.getByRole("alert").getAttribute("aria-live")).toBe("assertive");
    fireEvent.click(screen.getByText("되돌리기"));
    expect(onUndo).toHaveBeenCalled();
    expect(screen.queryByText("저장됨")).toBeNull();
    fireEvent.click(screen.getByText("푸시"));
    act(() => {
      vi.advanceTimersByTime(8001);
    });
    expect(screen.queryByText("저장됨")).toBeNull();
  });
  it("Provider 밖에서는 아무 일도 하지 않는다", () => {
    render(<Pusher onUndo={() => {}} />);
    fireEvent.click(screen.getByText("푸시"));
  });
});

describe("Tabs", () => {
  const tabs = [
    { id: "x", label: "하나", content: <p>내용1</p> },
    { id: "y", label: "둘", content: <p>내용2</p> },
    { id: "z", label: "셋", content: <p>내용3</p>, disabled: true },
  ];
  it("tablist, ←→ Home End 이동, 비활성 탭은 건너뜀", () => {
    const onChange = vi.fn();
    render(<Tabs tabs={tabs} ariaLabel="구역" onChange={onChange} />);
    expect(screen.getByRole("tablist", { name: "구역" })).toBeTruthy();
    const first = screen.getByRole("tab", { name: "하나" });
    expect(first.getAttribute("aria-selected")).toBe("true");
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("y");
    expect(screen.getByRole("tab", { name: "둘" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "둘" }), { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("x");
    expect(screen.getByRole("tabpanel", { name: "하나" })).toBeTruthy();
  });
  it("lazy: 선택 전 탭은 렌더하지 않는다", () => {
    render(<Tabs tabs={tabs} ariaLabel="구역" lazy />);
    expect(screen.queryByText("내용2")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "둘" }));
    expect(screen.getByText("내용2")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "하나" }));
    expect(screen.getByText("내용2")).toBeTruthy();
  });
  it("제어형 activeId", () => {
    render(<Tabs tabs={tabs} ariaLabel="구역" activeId="y" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "둘" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("ProvenanceBadge", () => {
  it("색 슬롯은 index mod 6, 라벨은 항상 보인다(임의 층 이름)", () => {
    const { container } = render(<ProvenanceBadge layer={{ id: "임의", label: "임의 층", index: 8 }} variant="set" />);
    const el = container.querySelector(".ac-prov")!;
    expect(el.getAttribute("data-slot")).toBe("2");
    expect(screen.getByText("임의 층")).toBeTruthy();
  });
  it("상속됨은 ↳, mixed는 층 수, onClick이 있으면 버튼", () => {
    const onClick = vi.fn();
    const layer = { id: "q", label: "큐", index: 0 };
    const { container } = render(<ProvenanceBadge layer={layer} variant="inherited" onClick={onClick} />);
    expect(container.textContent).toContain("↳");
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
    cleanup();
    render(<ProvenanceBadge layer={layer} variant="mixed" count={3} />);
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("Gauge", () => {
  it("값이 있으면 role=meter와 폭, 범위를 넘으면 자른다", () => {
    const { container } = render(<Gauge value={1.4} label="사용률" noValueLabel="정보 없음" />);
    const meter = screen.getByRole("meter", { name: "사용률" });
    expect(meter.getAttribute("aria-valuenow")).toBe("1");
    expect((container.querySelector(".ac-gauge-fill") as HTMLElement).style.width).toBe("100%");
  });
  it("값이 없으면 meter가 아니고 0%를 그리지 않는다", () => {
    const { container } = render(<Gauge label="사용률" noValueLabel="정보 없음" />);
    expect(screen.queryByRole("meter")).toBeNull();
    expect(container.querySelector(".ac-gauge-fill")).toBeNull();
    expect(screen.getByRole("img", { name: "사용률: 정보 없음" })).toBeTruthy();
  });
  it("stale 표시와 0 값은 값 있음", () => {
    const { container } = render(<Gauge value={0} stale label="l" noValueLabel="n" />);
    expect(screen.getByRole("meter").getAttribute("aria-valuenow")).toBe("0");
    expect(container.querySelector(".ac-gauge")?.getAttribute("data-stale")).toBe("true");
  });
});

describe("EmptyState", () => {
  it("제목·설명·액션·보조 액션·체크리스트", () => {
    render(
      <EmptyState
        title="비어 있음"
        description="설명"
        action={<button>만들기</button>}
        secondaryAction={<button>가져오기</button>}
        steps={[{ label: "첫째", done: true }, { label: "둘째", done: false, action: <button>하기</button> }]}
        doneLabel="완료"
      />,
    );
    expect(screen.getByRole("heading", { name: "비어 있음" })).toBeTruthy();
    expect(screen.getByText("가져오기")).toBeTruthy();
    expect(screen.getAllByRole("listitem").length).toBe(2);
    expect(screen.getByText("완료")).toBeTruthy();
  });
});
