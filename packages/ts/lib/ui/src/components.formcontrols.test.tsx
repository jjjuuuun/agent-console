import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Choice, Switch } from "./index";

afterEach(cleanup);

describe("Switch", () => {
  it("role=switch, aria-checked, 라벨과 켜짐/꺼짐 글자 단서", () => {
    const onChange = vi.fn();
    const { rerender } = render(<Switch checked={false} onChange={onChange} label="자동 실행" onText="켜짐" offText="꺼짐" />);
    const sw = screen.getByRole("switch", { name: "자동 실행" });
    expect(sw.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText("꺼짐")).toBeTruthy();
    fireEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(true);
    rerender(<Switch checked onChange={onChange} label="자동 실행" onText="켜짐" offText="꺼짐" />);
    expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("켜짐")).toBeTruthy();
  });
  it("라벨이 없으면 ariaLabel, disabled면 토글하지 않는다", () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} ariaLabel="알림" onText="켜짐" offText="꺼짐" disabled />);
    fireEvent.click(screen.getByRole("switch", { name: "알림" }));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Choice", () => {
  it("체크박스·라디오는 라벨로 이름을 얻는다", () => {
    render(<><Choice defaultChecked>동의</Choice><Choice kind="radio" name="g" value="a">가</Choice></>);
    expect(screen.getByRole("checkbox", { name: "동의" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "가" })).toBeTruthy();
  });
});

describe("tokens.css 10b 폼 컨트롤 기본", () => {
  const css = readFileSync(join(import.meta.dirname, "tokens.css"), "utf8");
  it("전역 입력 규칙이 체크박스·라디오를 제외하고 명시도 0(:where)이다", () => {
    expect(css).toMatch(/:where\(input:not\(\[type="checkbox"\], \[type="radio"\]/);
  });
  it("체크박스·라디오·select는 네이티브 모양을 끄고 포커스 링이 있다", () => {
    expect(css).toMatch(/:where\(input\[type="checkbox"\], input\[type="radio"\]\) \{\s*appearance: none/);
    expect(css).toMatch(/:where\(select\) \{\s*appearance: none/);
    expect(css).toMatch(/input\[type="checkbox"\], input\[type="radio"\]\):focus-visible/);
  });
  it("체크 표시·쉐브론 이미지가 세 테마 블록(다크·라이트·시스템 라이트)에 있다", () => {
    expect(css.match(/--ac-check-img:/g)?.length).toBe(3);
    expect(css.match(/--ac-chevron-img:/g)?.length).toBe(3);
  });
});
