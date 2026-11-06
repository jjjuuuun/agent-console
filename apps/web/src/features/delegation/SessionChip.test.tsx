import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IconRegistryProvider } from "@agent-console/ui";
import { appIcons } from "../../app/icons";
import { SessionChip } from "./index";

afterEach(cleanup);
const withIcons = (node: React.ReactNode) => <IconRegistryProvider icons={appIcons}>{node}</IconRegistryProvider>;

describe("SessionChip", () => {
  it("값이 null이면 아무것도 그리지 않는다", () => {
    const { container } = render(withIcons(<SessionChip value={null} />));
    expect(container.textContent).toBe("");
  });
  it("별도 세션은 글자·아이콘·실선, 같은 세션은 점선 구분(data 속성)이고 툴팁이 위임자를 말한다", () => {
    render(withIcons(<><SessionChip value="separate" /><SessionChip value="same" delegatorLabel="리더" /></>));
    expect(screen.getByText("별도 세션").closest(".ses-chip")!.getAttribute("data-session")).toBe("separate");
    const same = screen.getByText("같은 세션").closest(".ses-chip")!;
    expect(same.getAttribute("data-session")).toBe("same");
    expect(same.getAttribute("title")).toContain("리더 세션 안에서 실행됩니다");
    expect(same.querySelector("svg")).toBeTruthy();
  });
  it("모르는 값은 원문과 중립 스타일", () => {
    render(withIcons(<SessionChip value="x1" />));
    expect(screen.getByText("x1").closest(".ses-chip")!.getAttribute("data-session")).toBe("other");
  });
  it("icon 변형은 접근성 이름에 글자를 담고, onClick이 있으면 단추다", () => {
    const onClick = vi.fn();
    render(withIcons(<><SessionChip value="separate" variant="icon" /><SessionChip value="same" variant="icon" onClick={onClick} /></>));
    expect(screen.getByRole("img", { name: /별도 세션/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /같은 세션/ }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
