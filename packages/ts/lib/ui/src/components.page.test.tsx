import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AttachmentList,
  CommandPalette,
  Disclosure,
  Icon,
  IconRegistryProvider,
  ListPane,
  PageHeader,
  TrustBadge,
  createIconRegistry,
  filterCommandGroups,
  formatKeyCombo,
  iconRegistry,
  matchKeyCombo,
  registerIcons,
  useKeyCombo,
  type AttachmentGroup,
  type CommandGroup,
} from "./index";

afterEach(cleanup);

describe("PageHeader", () => {
  it("제목 h1, breadcrumb 마지막이 현재 위치, 슬롯", () => {
    render(
      <PageHeader title="팀 구성" breadcrumb={[{ label: "목록", href: "#/t" }, { label: "A" }]} breadcrumbLabel="경로" status={<span>저장됨</span>} actions={<button type="button">저장</button>} />,
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("팀 구성");
    expect(screen.getByRole("navigation", { name: "경로" })).toBeTruthy();
    expect(screen.getByText("목록").closest("a")?.getAttribute("href")).toBe("#/t");
    expect(screen.getByText("A").closest("li")?.getAttribute("aria-current")).toBe("page");
    expect(screen.getByText("저장됨")).toBeTruthy();
    expect(screen.getByRole("button", { name: "저장" })).toBeTruthy();
  });
  it("breadcrumb 없으면 nav 없음", () => {
    render(<PageHeader title="x" />);
    expect(screen.queryByRole("navigation")).toBeNull();
  });
});

describe("TrustBadge", () => {
  it("알려진 값·모르는 값 모두 data-trust와 라벨을 보인다(모르는 값은 원문 폴백)", () => {
    render(
      <>
        <TrustBadge trust="official" label="공식" />
        <TrustBadge trust="brand-new-level" />
      </>,
    );
    expect(screen.getByText("공식").closest("[data-trust]")?.getAttribute("data-trust")).toBe("official");
    expect(screen.getByText("brand-new-level").closest("[data-trust]")?.getAttribute("data-trust")).toBe("brand-new-level");
  });
});

describe("Disclosure", () => {
  it("비제어: 요약 클릭으로 토글, onOpenChange", () => {
    const onOpenChange = vi.fn();
    const { container } = render(<Disclosure summary="자세히" onOpenChange={onOpenChange}>내용</Disclosure>);
    const details = container.querySelector("details")!;
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText("자세히"));
    expect(details.open).toBe(true);
    expect(onOpenChange).toHaveBeenLastCalledWith(true);
  });
  it("제어형: open이 바뀌지 않으면 열리지 않는다", () => {
    const onOpenChange = vi.fn();
    const { container } = render(<Disclosure summary="s" open={false} onOpenChange={onOpenChange}>c</Disclosure>);
    fireEvent.click(screen.getByText("s"));
    expect(onOpenChange).toHaveBeenCalledWith(true);
    expect(container.querySelector("details")!.open).toBe(false);
  });
});

describe("Icon / 레지스트리", () => {
  const Star = ({ size }: { size?: number }) => <svg data-testid="star" width={size} />;
  it("기본 레지스트리는 앱 고정 이름을 가지고, registerIcons는 원본을 바꾸지 않는다", () => {
    const next = registerIcons({ star: Star });
    expect(next.has("star")).toBe(true);
    expect(iconRegistry.has("star")).toBe(false);
    expect(iconRegistry.has("lock")).toBe(true);
  });
  it("Provider로 주입한 이름을 그리고, 중첩은 상위를 유지한 채 더한다", () => {
    render(
      <IconRegistryProvider icons={{ star: Star }}>
        <IconRegistryProvider icons={{}}>
          <Icon name="star" size={20} />
        </IconRegistryProvider>
      </IconRegistryProvider>,
    );
    expect(screen.getByTestId("star").getAttribute("width")).toBe("20");
  });
  it("registry prop으로 통째로 교체할 수 있다", () => {
    render(
      <IconRegistryProvider registry={createIconRegistry({ star: Star })}>
        <Icon name="lock" fallbackText="락" />
      </IconRegistryProvider>,
    );
    expect(screen.queryByTestId("star")).toBeNull();
    expect(screen.getByText("락".toUpperCase())).toBeTruthy(); // 레지스트리에 없어 아바타
  });
  it("모르는 이름은 첫 글자 아바타, 텍스트도 없으면 아무것도 그리지 않는다", () => {
    const { container, rerender } = render(<Icon name="nope" fallbackText="reviewer" />);
    expect(container.querySelector("[data-fallback]")?.textContent).toBe("R");
    rerender(<Icon name="nope" />);
    expect(container.firstChild).toBeNull();
  });
  it("label이 있으면 role=img, 없으면 aria-hidden", () => {
    const { container, rerender } = render(<Icon name="lock" label="잠김" />);
    expect(screen.getByRole("img", { name: "잠김" })).toBeTruthy();
    rerender(<Icon name="lock" />);
    expect(container.querySelector("[aria-hidden='true']")).toBeTruthy();
  });
});

type Row = { id: string; name: string };
const rows: Row[] = [{ id: "a", name: "가" }, { id: "b", name: "나" }, { id: "c", name: "다" }];
const lpMessages = { listLabel: "목록", searchLabel: "검색" };

describe("ListPane", () => {
  it("listbox/option, 선택 표시, Tab 정지점은 선택 항목 하나", () => {
    render(<ListPane items={rows} selectedId="b" onSelect={() => {}} renderItem={(r) => r.name} messages={lpMessages} />);
    expect(screen.getByRole("listbox", { name: "목록" })).toBeTruthy();
    const opts = screen.getAllByRole("option");
    expect(opts.map((o) => o.getAttribute("aria-selected"))).toEqual(["false", "true", "false"]);
    expect(opts.filter((o) => o.tabIndex === 0).map((o) => o.textContent)).toEqual(["나"]);
  });
  it("↑↓ Home End로 포커스 이동, Enter로 선택, 클릭 선택", () => {
    const onSelect = vi.fn();
    render(<ListPane items={rows} selectedId="a" onSelect={onSelect} renderItem={(r) => r.name} messages={lpMessages} />);
    const first = screen.getByText("가");
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("나");
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement?.textContent).toBe("다");
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith("c", rows[2]);
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement?.textContent).toBe("가");
    fireEvent.click(screen.getByText("나"));
    expect(onSelect).toHaveBeenLastCalledWith("b", rows[1]);
  });
  it("검색 입력과 로딩/오류/빈 슬롯 우선순위", () => {
    const onSearch = vi.fn();
    const { rerender } = render(<ListPane items={[]} onSelect={() => {}} renderItem={() => null} searchValue="" onSearchChange={onSearch} empty={<p>비었음</p>} messages={lpMessages} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "검색" }), { target: { value: "q" } });
    expect(onSearch).toHaveBeenCalledWith("q");
    expect(screen.getByText("비었음")).toBeTruthy();
    rerender(<ListPane items={rows} onSelect={() => {}} renderItem={() => null} loading={<p>불러오는 중</p>} empty={<p>비었음</p>} messages={lpMessages} />);
    expect(screen.getByRole("status").textContent).toBe("불러오는 중");
    rerender(<ListPane items={rows} onSelect={() => {}} renderItem={() => null} loading={<p>불러오는 중</p>} error={<p>실패</p>} messages={lpMessages} />);
    expect(screen.getByRole("alert").textContent).toBe("실패");
  });
  it("검색창에서 ↓ 누르면 목록으로 이동", () => {
    render(<ListPane items={rows} selectedId="b" onSelect={() => {}} renderItem={(r) => r.name} searchValue="" onSearchChange={() => {}} messages={lpMessages} />);
    const search = screen.getByRole("searchbox");
    search.focus();
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("나");
  });
});

const amessages = { moveUp: "위로", moveDown: "아래로", remove: "삭제", modeLabel: "방식", add: "추가", empty: "없음", readOnly: "읽기 전용" };
const agroups: AttachmentGroup[] = [
  { layer: { id: "team", label: "팀", index: 1 }, editable: true, items: [{ key: "k1", title: "첫째", mode: "m1" }, { key: "k2", title: "둘째", mode: "m2" }] },
  { layer: { id: "base", label: "기본", index: 0 }, editable: false, items: [{ key: "k3", title: "상속", mode: "m1" }] },
];

describe("AttachmentList", () => {
  it("편집 가능한 층만 조작 버튼이 있고 읽기 전용 표시", () => {
    render(<AttachmentList groups={agroups} messages={amessages} onReorder={() => {}} onRemove={() => {}} />);
    expect(screen.getByRole("button", { name: "삭제: 첫째" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "삭제: 상속" })).toBeNull();
    expect(screen.getByText("읽기 전용")).toBeTruthy();
    expect((screen.getByRole("button", { name: "위로: 첫째" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("순서·삭제·방식·추가 콜백", () => {
    const cb = { onReorder: vi.fn(), onRemove: vi.fn(), onModeChange: vi.fn(), onAdd: vi.fn() };
    render(<AttachmentList groups={agroups} messages={amessages} modeOptions={[{ value: "m1", label: "참조" }, { value: "m2", label: "포함" }]} {...cb} />);
    fireEvent.click(screen.getByRole("button", { name: "아래로: 첫째" }));
    expect(cb.onReorder).toHaveBeenCalledWith("team", ["k2", "k1"]);
    fireEvent.click(screen.getByRole("button", { name: "삭제: 둘째" }));
    expect(cb.onRemove).toHaveBeenCalledWith("team", "k2");
    fireEvent.change(screen.getByRole("combobox", { name: "방식: 첫째" }), { target: { value: "m2" } });
    expect(cb.onModeChange).toHaveBeenCalledWith("team", "k1", "m2");
    fireEvent.click(screen.getByRole("button", { name: "추가" }));
    expect(cb.onAdd).toHaveBeenCalledWith("team");
  });
  it("행 렌더 슬롯과 빈 층 문구, 모르는 방식은 원문", () => {
    render(
      <AttachmentList
        groups={[{ layer: { id: "x", label: "X", index: 2 }, editable: false, items: [{ key: "z", title: "t", mode: "weird" }] }, { layer: { id: "y", label: "Y", index: 3 }, editable: true, items: [] }]}
        messages={amessages}
        renderRow={(a) => <b>{`행:${a.title}`}</b>}
      />,
    );
    expect(screen.getByText("행:t")).toBeTruthy();
    expect(screen.getByText("weird")).toBeTruthy();
    expect(screen.getByText("없음")).toBeTruthy();
  });
});

describe("키 조합", () => {
  const ev = (o: Partial<KeyboardEvent> & { key: string }) => ({ ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...o });
  it("Ctrl+K / Mod / Alt+J / 정확 일치", () => {
    expect(matchKeyCombo(ev({ key: "k", ctrlKey: true }), "Ctrl+K")).toBe(true);
    expect(matchKeyCombo(ev({ key: "K", ctrlKey: true }), "ctrl+k")).toBe(true);
    expect(matchKeyCombo(ev({ key: "k", ctrlKey: true, shiftKey: true }), "Ctrl+K")).toBe(false);
    expect(matchKeyCombo(ev({ key: "k", metaKey: true }), "Mod+K", "mac")).toBe(true);
    expect(matchKeyCombo(ev({ key: "k", ctrlKey: true }), "Mod+K", "mac")).toBe(false);
    expect(matchKeyCombo(ev({ key: "j", altKey: true }), "Alt+J")).toBe(true);
    expect(matchKeyCombo(ev({ key: "Escape" }), "Esc")).toBe(true);
    expect(matchKeyCombo(ev({ key: "k" }), "")).toBe(false);
  });
  it("IME 조합 중에는 일치하지 않는다", () => {
    expect(matchKeyCombo(ev({ key: "k", ctrlKey: true, isComposing: true }), "Ctrl+K")).toBe(false);
  });
  it("표시 형식", () => {
    expect(formatKeyCombo("Mod+K", "mac")).toBe("⌘K");
    expect(formatKeyCombo("Ctrl+Shift+b")).toBe("Ctrl+Shift+B");
  });
  it("useKeyCombo: 설정으로 바뀐 키로 동작하고 기본 동작을 막는다", () => {
    const run = vi.fn();
    function Host({ combo }: { combo: string }) {
      useKeyCombo(combo, run);
      return null;
    }
    const { rerender } = render(<Host combo="Ctrl+K" />);
    const e1 = new KeyboardEvent("keydown", { key: "k", ctrlKey: true, cancelable: true });
    window.dispatchEvent(e1);
    expect(run).toHaveBeenCalledTimes(1);
    expect(e1.defaultPrevented).toBe(true);
    rerender(<Host combo="Alt+P" />);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
    expect(run).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "p", altKey: true }));
    expect(run).toHaveBeenCalledTimes(2);
  });
});

describe("CommandPalette", () => {
  const messages = { title: "빠른 이동", inputLabel: "명령 검색", empty: "일치하는 항목이 없습니다", loading: "불러오는 중" };
  function groupsWith(run: (id: string) => void): CommandGroup[] {
    return [
      { id: "g1", title: "화면", items: [{ id: "a", label: "채팅", hint: "c", run: () => run("a") }, { id: "b", label: "팀 구성", shortcut: "G T", run: () => run("b") }] },
      { id: "g2", title: "동작", items: [{ id: "c", label: "새 대화", badge: <span>칩</span>, run: () => run("c") }, { id: "d", label: "막힘", disabled: true, run: () => run("d") }] },
    ];
  }
  function Host({ run, onClose = () => {} }: { run: (id: string) => void; onClose?: () => void }) {
    const [q, setQ] = useState("");
    return <CommandPalette open onClose={onClose} groups={filterCommandGroups(groupsWith(run), q)} query={q} onQueryChange={setQ} messages={messages} />;
  }

  it("닫혀 있으면 아무것도 그리지 않는다", () => {
    render(<CommandPalette open={false} onClose={() => {}} groups={[]} query="" onQueryChange={() => {}} messages={messages} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("combobox + listbox + option 구조, 그룹 이름, activedescendant", () => {
    render(<Host run={() => {}} />);
    const input = screen.getByRole("combobox", { name: "명령 검색" });
    expect(document.activeElement).toBe(input);
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(screen.getByRole("group", { name: "화면" })).toBeTruthy();
    const opts = screen.getAllByRole("option");
    expect(opts).toHaveLength(4);
    expect(input.getAttribute("aria-activedescendant")).toBe(opts[0]!.id);
    expect(opts[0]!.getAttribute("aria-selected")).toBe("true");
  });
  it("↑↓는 비활성 항목을 건너뛰며 순환하고 Enter로 실행(닫은 뒤)", () => {
    const run = vi.fn();
    const onClose = vi.fn();
    render(<Host run={run} onClose={onClose} />);
    const input = screen.getByRole("combobox");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getByText("새 대화").closest("[role=option]")?.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(input, { key: "ArrowDown" }); // 막힘 건너뛰고 처음으로
    expect(screen.getByText("채팅").closest("[role=option]")?.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onClose).toHaveBeenCalled();
    expect(run).toHaveBeenCalledWith("c");
  });
  it("한글 IME 조합 중 Enter는 무시한다(isComposing, keyCode 229, composition 이벤트)", () => {
    const run = vi.fn();
    render(<Host run={run} />);
    const input = screen.getByRole("combobox");
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(run).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input);
  });
  it("Esc로 닫고, 클릭으로 실행하며, 검색어로 걸러지고 결과 없으면 문구", () => {
    const run = vi.fn();
    const onClose = vi.fn();
    render(<Host run={run} onClose={onClose} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "팀" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    fireEvent.click(screen.getByText("팀 구성"));
    expect(run).toHaveBeenCalledWith("b");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "zzz" } });
    expect(screen.getByText("일치하는 항목이 없습니다")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
  it("그룹 로딩 줄, 모달 중 배경 inert", () => {
    const outside = document.createElement("div");
    document.body.appendChild(outside);
    render(<CommandPalette open onClose={() => {}} groups={groupsWith(() => {}).slice(0, 1)} query="" onQueryChange={() => {}} loading={{ g1: true, g3: true }} messages={messages} />);
    expect(screen.getAllByText("불러오는 중")).toHaveLength(2);
    expect(outside.hasAttribute("inert")).toBe(true);
    cleanup();
    expect(outside.hasAttribute("inert")).toBe(false);
    outside.remove();
  });
  it("filterCommandGroups: 부분 일치·그룹당 제한", () => {
    const g = groupsWith(() => {});
    expect(filterCommandGroups(g, "대화").map((x) => x.id)).toEqual(["g2"]);
    expect(filterCommandGroups(g, "", 1).map((x) => x.items.length)).toEqual([1, 1]);
  });
});

describe("StepGuide·QuickStartRow (5.2R.10)", () => {
  it("처음 미완료 단계만 current, 완료는 버튼 없음, 단계 0개면 비어 있음", async () => {
    const { StepGuide } = await import("./index");
    const onAction = vi.fn();
    const { container, rerender } = render(
      <StepGuide
        messages={{ stepsLabel: "순서", go: "가기", done: "완료" }}
        steps={[
          { id: "a", label: "하나", done: true, to: "/a" },
          { id: "b", label: "둘", done: false, onAction },
          { id: "c", label: "셋", done: false, to: "/c" },
        ]}
      />,
    );
    expect(container.querySelectorAll('[data-current="true"]').length).toBe(1);
    expect(container.querySelector('[data-step="b"]')?.getAttribute("data-current")).toBe("true");
    expect(container.querySelector('[data-step="a"] .ac-btn')).toBeNull();
    expect(container.querySelector('[data-step="c"] a')?.getAttribute("href")).toBe("/c");
    fireEvent.click(container.querySelector('[data-step="b"] button')!);
    expect(onAction).toHaveBeenCalledOnce();
    rerender(<StepGuide messages={{ stepsLabel: "순서", go: "가기", done: "완료" }} steps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("QuickStartRow: 항목 0개면 비어 있고, 시작 버튼이 id를 넘긴다", async () => {
    const { QuickStartRow } = await import("./index");
    const onStart = vi.fn();
    const { container, rerender } = render(<QuickStartRow title="바로 시작" startLabel="시작" items={[{ id: "p", title: "체험", badges: ["체험"] }]} onStart={onStart} />);
    fireEvent.click(screen.getByRole("button", { name: "체험 시작" }));
    expect(onStart).toHaveBeenCalledWith("p");
    rerender(<QuickStartRow title="바로 시작" startLabel="시작" items={[]} onStart={onStart} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("MiddleEllipsis (5.2R.16)", () => {
  it("긴 값은 앞 8·뒤 4만 남기고 전체는 툴팁, 짧은 값은 그대로", async () => {
    const { MiddleEllipsis, middleEllipsis } = await import("./index");
    expect(middleEllipsis("abcdefgh0123456789wxyz")).toBe("abcdefgh…wxyz");
    expect(middleEllipsis("short-id")).toBe("short-id");
    const { container } = render(<MiddleEllipsis value="abcdefgh0123456789wxyz" />);
    expect(container.textContent).toBe("abcdefgh…wxyz");
    expect(container.querySelector("[title='abcdefgh0123456789wxyz']")).not.toBeNull();
  });
  it("copyLabel이 있으면 복사 버튼이 전체 값을 클립보드에 쓴다", async () => {
    const { MiddleEllipsis } = await import("./index");
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<MiddleEllipsis value="abcdefgh0123456789wxyz" copyLabel="복사" />);
    fireEvent.click(screen.getByRole("button", { name: "복사" }));
    expect(writeText).toHaveBeenCalledWith("abcdefgh0123456789wxyz");
  });
});
