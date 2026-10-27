import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Badge, Banner, Button, IconButton, StatusChip, StatusIcon, Tag, ThemeProvider } from "./index";

afterEach(cleanup);

describe("StatusIcon / StatusChip", () => {
  it("data-status만 달고 임의 문자열도 그대로 전달한다(JS 상태 표 없음)", () => {
    const { container } = render(<StatusIcon status="알수없음-xyz" />);
    const el = container.querySelector(".ac-status-icon")!;
    expect(el.getAttribute("data-status")).toBe("알수없음-xyz");
    expect(el.getAttribute("aria-hidden")).toBe("true");
  });

  it("label이 있으면 접근성 이름이 된다", () => {
    render(<StatusIcon status="running" label="실행 중" />);
    expect(screen.getByRole("img", { name: "실행 중" })).toBeTruthy();
  });

  it("칩은 라벨을 보이고, 라벨 생략 시 상태 원문을 쓴다", () => {
    render(<StatusChip status="succeeded" label="성공" />);
    expect(screen.getByText("성공").className).toContain("ac-ellipsis");
    render(<StatusChip status="brand-new" />);
    expect(screen.getByText("brand-new")).toBeTruthy();
  });

  it("compact 칩은 아이콘만 보이고 aria-label을 가진다", () => {
    const { container } = render(<StatusChip status="failed" label="실패" compact />);
    expect(screen.getByRole("img", { name: "실패" })).toBeTruthy();
    expect(container.querySelector(".ac-status-chip-label")).toBeNull();
  });

  it("Run 상태는 data-status-kind=run을 병기한다", () => {
    const { container } = render(<StatusChip status="interrupted" kind="run" label="중단됨" />);
    const chip = container.querySelector(".ac-status-chip")!;
    expect(chip.getAttribute("data-status-kind")).toBe("run");
    expect(chip.getAttribute("data-status")).toBe("interrupted");
  });
});

describe("Button / IconButton", () => {
  it("클릭을 전달하고 기본 type=button", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick} variant="primary">저장</Button>);
    const b = screen.getByRole("button", { name: "저장" });
    expect(b.getAttribute("type")).toBe("button");
    fireEvent.click(b);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("loading이면 aria-busy, 클릭 불가, 라벨 폭 유지(라벨은 남아 있음)", () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>저장</Button>);
    const b = screen.getByRole("button", { name: /저장/ });
    expect(b.getAttribute("aria-busy")).toBe("true");
    expect((b as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByText("저장").closest("button")).toBe(b); // 라벨이 DOM(접근성 트리)에 남는다
  });

  it("IconButton은 label을 aria-label/title로 쓴다", () => {
    render(<IconButton label="삭제" icon={<svg />} />);
    const b = screen.getByRole("button", { name: "삭제" });
    expect(b.getAttribute("title")).toBe("삭제");
  });
});

describe("Banner / Badge / Tag", () => {
  it("danger 배너는 role=alert, 아이콘 마크를 가진다", () => {
    const { container } = render(<Banner tone="danger" title="오류">저장하지 못했습니다</Banner>);
    expect(screen.getByRole("alert").textContent).toContain("저장하지 못했습니다");
    expect(container.querySelector(".ac-banner-mark")).toBeTruthy();
  });
  it("Tag는 긴 텍스트의 전체 값을 title로 제공한다", () => {
    render(<Tag>가나다라마바사아자차카타파하</Tag>);
    expect(screen.getByTitle("가나다라마바사아자차카타파하")).toBeTruthy();
    render(<Badge tone="info">3</Badge>);
    expect(screen.getByText("3").getAttribute("data-tone")).toBe("info");
  });
});

describe("ThemeProvider", () => {
  it("data-theme를 적용하고 system이면 제거한다", () => {
    const target = document.createElement("div");
    const { rerender } = render(<ThemeProvider theme="light" onThemeChange={() => {}} target={target} />);
    expect(target.getAttribute("data-theme")).toBe("light");
    rerender(<ThemeProvider theme="system" onThemeChange={() => {}} target={target} />);
    expect(target.hasAttribute("data-theme")).toBe(false);
  });
});
