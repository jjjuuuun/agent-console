import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LanguageSelect, type LanguageOption, type LanguageSelectMessages, type LanguageSelectProps } from "./LanguageSelect";

afterEach(cleanup);

const messages: LanguageSelectMessages = {
  label: "Language",
  auto: "Automatic",
  autoNow: (name) => `Now: ${name}`,
  autoFallback: (code, name) => `${code} unavailable, ${name}`,
  partial: "Partly translated",
  partialHint: (name, missing) => `Missing text appears in ${name}${missing ? ` (${missing})` : ""}`,
  sources: (list) => `Source: ${list.join(", ")}`,
  unavailable: (code) => `${code} (unavailable)`,
  unavailableHelp: "Saved language isn't available",
  loading: "Loading…",
  search: "Find a language",
  pending: "Applying",
};
const opt = (code: string, name = code, extra: Partial<LanguageOption> = {}): LanguageOption => ({ code, name, complete: true, sources: [], ...extra });
const base = (over: Partial<LanguageSelectProps> = {}): LanguageSelectProps => ({
  options: [opt("en", "English"), opt("ko", "한국어")],
  value: null,
  autoHint: { resolvedName: "English" },
  fallbackName: "English",
  onChange: vi.fn(),
  messages,
  ...over,
});
const many = (n: number) => Array.from({ length: n }, (_, i) => opt(`l${String(i).padStart(2, "0")}`, `Lang ${i}`, { aliases: [`alias${i}`] }));

describe("LanguageSelect: 라디오 목록(선택지 6개 이하)", () => {
  it("자동이 첫 항목이고 이름에 lang이 붙으며 누르면 onChange", () => {
    const props = base({ value: "en" });
    render(<LanguageSelect {...props} />);
    const list = screen.getByRole("radiogroup", { name: "Language" });
    const radios = within(list).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.value)).toEqual([" auto".replace(" ", "\u0000"), "en", "ko"]);
    expect(radios[1]!.checked).toBe(true);
    expect(screen.getByText("한국어").getAttribute("lang")).toBe("ko");
    fireEvent.click(radios[2]!);
    expect(props.onChange).toHaveBeenCalledWith("ko");
    fireEvent.click(radios[0]!);
    expect(props.onChange).toHaveBeenCalledWith(null);
  });

  it("부분 번역 칩은 글자와 정보 표시로 알리고 툴팁에 대체 언어를 말한다. 출처는 코드 옆에", () => {
    render(<LanguageSelect {...base({ options: [opt("en", "English"), opt("de", "Deutsch", { complete: false, missing: 3, sources: ["user-folder"] })] })} />);
    expect(screen.getByText("Partly translated").closest("[title]")?.getAttribute("title")).toBe("Missing text appears in English (3)");
    expect(screen.getByText("Source: user-folder")).toBeTruthy();
  });

  it("적용 중인 선택에는 스피너, 선택 표시는 즉시 옮겨 있다", () => {
    render(<LanguageSelect {...base({ value: "en", pending: "ko" })} />);
    expect((document.querySelector('input[value="ko"]') as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("status", { name: "Applying" })).toBeTruthy();
    expect(document.querySelector(".app-lang")?.getAttribute("aria-busy")).toBe("true");
  });

  it("목록에 없는 저장값은 선택된 비활성 행과 안내", () => {
    render(<LanguageSelect {...base({ value: "zz", unavailableValue: "zz" })} />);
    const row = screen.getByText("zz (unavailable)").closest("label")!;
    expect((row.querySelector("input") as HTMLInputElement).checked).toBe(true);
    expect((row.querySelector("input") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("Saved language isn't available")).toBeTruthy();
  });

  it("Home·End는 처음·끝 행을 고른다", () => {
    const props = base({ value: "en" });
    render(<LanguageSelect {...props} />);
    const list = screen.getByRole("radiogroup");
    fireEvent.keyDown(list, { key: "End" });
    expect(props.onChange).toHaveBeenLastCalledWith("ko");
    fireEvent.keyDown(list, { key: "Home" });
    expect(props.onChange).toHaveBeenLastCalledWith(null);
  });

  it("로딩 중에는 불러오는 중 줄과 aria-busy", () => {
    render(<LanguageSelect {...base({ loading: true })} />);
    expect(screen.getByText("Loading…")).toBeTruthy();
  });

  it("경계값은 props다: inlineMax를 줄이면 같은 3개가 팝오버가 된다", () => {
    render(<LanguageSelect {...base({ inlineMax: 2 })} />);
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.getByRole("button", { name: /Language/ })).toBeTruthy();
  });
});

describe("LanguageSelect: 팝오버 목록(선택지 7개 이상)", () => {
  const open = (props: LanguageSelectProps) => {
    render(<LanguageSelect {...props} />);
    const trigger = screen.getByRole("button", { name: /Language/ });
    fireEvent.click(trigger);
    return trigger;
  };

  it("트리거에 현재 이름, 열면 listbox, 항목을 누르면 고르고 닫는다", () => {
    const props = base({ options: many(7), value: "l02" });
    const trigger = open(props);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const box = screen.getByRole("listbox", { name: "Language" });
    expect(within(box).getAllByRole("option")).toHaveLength(8);
    expect(within(box).getByRole("option", { selected: true }).textContent).toContain("Lang 2");
    fireEvent.click(within(box).getByText("Lang 4"));
    expect(props.onChange).toHaveBeenCalledWith("l04");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("검색 입력은 13개 이상일 때만, 이름·코드·다른 이름(별칭)으로 찾는다", () => {
    const small = base({ options: many(7) });
    open(small);
    expect(screen.queryByRole("searchbox")).toBeNull();
    cleanup();
    const props = base({ options: many(14) });
    open(props);
    const input = screen.getByRole("searchbox", { name: "Find a language" });
    fireEvent.change(input, { target: { value: "ALIAS7" } });
    const box = screen.getByRole("listbox");
    expect(within(box).getAllByRole("option").map((o) => o.textContent)).toEqual(expect.arrayContaining([expect.stringContaining("Lang 7")]));
    expect(within(box).queryByText("Lang 3")).toBeNull();
    fireEvent.change(input, { target: { value: "l1" } });
    expect(within(box).getByText("Lang 10")).toBeTruthy();
  });

  it("키보드: ↓ + Enter로 고르고, Esc는 선택을 바꾸지 않고 닫아 트리거로 포커스를 돌린다", () => {
    const props = base({ options: many(7), value: null });
    const trigger = open(props);
    const box = screen.getByRole("listbox");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(props.onChange).toHaveBeenCalledWith("l00");
    cleanup();
    const props2 = base({ options: many(7), value: null });
    const trigger2 = open(props2);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    expect(props2.onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(trigger2);
    expect(trigger).toBeTruthy();
  });

  it("한글 조합 중 Enter는 선택하지 않는다", () => {
    const props = base({ options: many(14) });
    open(props);
    const input = screen.getByRole("searchbox");
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(props.onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
});
