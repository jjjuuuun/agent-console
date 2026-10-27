import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { ChipRow, ConfirmDialog, Dialog, Drawer, Gauge, IconButton, Sidebar, Tabs } from "./index";

/** 접근성 자동 점검(5.2R.44, ux-overhaul §13 표의 "자동" 항목): 이름 없는 버튼 0, 다이얼로그·서랍 포커스 복귀, meter. 대비 쌍은 tokens.test.ts, 1024x640 하단 버튼은 e2e 43. */
afterEach(cleanup);

/** aria-hidden 하위를 뺀 보이는 글자. */
function visibleText(el: Element): string {
  return [...el.childNodes].map((n) => (n.nodeType === 3 ? (n.textContent ?? "") : n instanceof Element && n.getAttribute("aria-hidden") !== "true" ? visibleText(n) : "")).join("");
}

/** 접근성 이름이 비어 있는 button 목록: aria-label/aria-labelledby도 없고 보이는 글자도 없다. */
function unnamedButtons(root: ParentNode): string[] {
  return [...root.querySelectorAll("button, [role=button]")]
    .filter((b) => {
      const label = b.getAttribute("aria-label")?.trim();
      const by = b.getAttribute("aria-labelledby");
      return !label && !by && !visibleText(b).trim();
    })
    .map((b) => b.outerHTML.slice(0, 120));
}

function Everything() {
  return (
    <div>
      <IconButton label="새로 만들기" icon={<span aria-hidden>+</span>} />
      <Sidebar
        items={[
          { id: "a", label: "에이전트", icon: <span aria-hidden>A</span> },
          { id: "s", label: "설정", position: "bottom", icon: <span aria-hidden>S</span> },
        ]}
        activeId="a"
        onNavigate={() => undefined}
        collapsed
        onCollapsedChange={() => undefined}
        messages={{ navLabel: "주 메뉴", collapse: "접기", expand: "펼치기" }}
      />
      <Tabs ariaLabel="탭" tabs={[{ id: "1", label: "하나", content: <div /> }, { id: "2", label: "둘", content: <div /> }]} />
      <ChipRow ariaLabel="칩" chips={[{ id: "c", label: "칩", onSelect: () => undefined }]} />
      <Dialog open title="제목" onClose={() => undefined} actions={<button>확인</button>}>
        본문
      </Dialog>
      <Drawer open title="서랍" closeLabel="닫기" onClose={() => undefined}>
        본문
      </Drawer>
    </div>
  );
}

describe("이름 없는 버튼 0 (§13-3)", () => {
  it("공용 컴포넌트를 접힌 상태로 모두 그려도 이름 없는 button이 없다(문서 전체, 포털 포함)", () => {
    render(<Everything />);
    expect(unnamedButtons(document.body)).toEqual([]);
  });
  it("ConfirmDialog 의 버튼도 모두 이름이 있다", () => {
    render(<ConfirmDialog open title="삭제?" confirmLabel="삭제" cancelLabel="취소" onConfirm={() => undefined} onCancel={() => undefined} danger />);
    expect(unnamedButtons(document.body)).toEqual([]);
  });
  it("검사기 자체: 아이콘만 있고 이름이 없는 버튼은 잡는다", () => {
    render(<button><span aria-hidden>x</span></button>);
    expect(unnamedButtons(document.body)).toHaveLength(1);
  });
});

function DialogHost() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>열기</button>
      <Dialog open={open} title="대화상자" onClose={() => setOpen(false)} actions={<button onClick={() => setOpen(false)}>닫기 버튼</button>}>
        <input aria-label="입력" />
      </Dialog>
    </div>
  );
}
function DrawerHost() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen(true)}>추가</button>
      <Drawer open={open} title="서랍" closeLabel="서랍 닫기" onClose={() => setOpen(false)}>
        <input aria-label="이름" />
      </Drawer>
    </div>
  );
}

describe("포커스 복귀 (§13-7, §13-13)", () => {
  it.each([
    ["Esc", () => fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })],
    ["하단 버튼", () => fireEvent.click(screen.getByText("닫기 버튼"))],
  ])("Dialog: 열기 → 포커스가 안으로 → %s로 닫으면 열었던 버튼으로 돌아온다", (_n, close) => {
    render(<DialogHost />);
    const trigger = screen.getByText("열기");
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
    close();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("Drawer: 머리 닫기 버튼으로 닫으면 [+ 추가] 로 돌아온다", () => {
    render(<DrawerHost />);
    const trigger = screen.getByText("추가");
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "서랍 닫기" }));
    expect(document.activeElement).toBe(trigger);
  });
});

describe("사용량 게이지 meter (§13-11)", () => {
  it("값이 있으면 role=meter + aria-valuenow/min/max + 이름, 값이 없으면 meter를 그리지 않는다", () => {
    const { rerender } = render(<Gauge value={0.42} label="5시간 사용률" noValueLabel="값 없음" />);
    const m = screen.getByRole("meter", { name: "5시간 사용률" });
    expect(m.getAttribute("aria-valuenow")).toBe("0.42");
    expect(m.getAttribute("aria-valuetext")).toBe("42%");
    expect(m.hasAttribute("aria-valuemin")).toBe(true);
    expect(m.hasAttribute("aria-valuemax")).toBe(true);
    rerender(<Gauge label="5시간 사용률" noValueLabel="값 없음" />);
    expect(screen.queryByRole("meter")).toBeNull();
  });
});
