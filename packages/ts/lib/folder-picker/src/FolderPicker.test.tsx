import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState, type ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FolderPicker, type FolderPickerProps } from "./FolderPicker";
import { checked, sampleEntries, sampleListing } from "./testing";
import type { FolderCheckFn, FolderCheckOutcome, FolderListFn } from "./types";

const ROOTS = [{ kind: "home", path: "/home/me", label: "홈" }, { kind: "root", path: "/", label: "루트" }];

function Harness(p: Partial<FolderPickerProps> & { check: FolderCheckFn; initial?: string }): ReactElement {
  const [v, setV] = useState(p.initial ?? "");
  const list: FolderListFn = p.list ?? (async (r) => sampleListing(r.path, []));
  return <FolderPicker id="fp" roots={ROOTS} defaultManualOpen {...p} list={list} value={v} onValueChange={setV} />;
}

const flush = async (ms = 0) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};
const input = () => screen.getByLabelText("폴더 경로") as HTMLInputElement;
const type = (v: string) => fireEvent.change(input(), { target: { value: v } });
const result = () => document.getElementById("fp-result")!;

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("확인 타이밍", () => {
  it("입력 300ms 뒤에 확인하고, 그 전에는 요청하지 않는다", async () => {
    const check = vi.fn<FolderCheckFn>(async () => checked({ path: "/srv/app" }));
    render(<Harness check={check} />);
    type("/srv/app");
    await flush(299);
    expect(check).not.toHaveBeenCalled();
    await flush(1);
    expect(check).toHaveBeenCalledTimes(1);
    expect(check.mock.calls[0]![0]).toEqual({ path: "/srv/app" });
    expect(result().getAttribute("data-state")).toBe("ok");
  });
  it("연속 입력은 마지막 값만 확인한다", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    render(<Harness check={check} />);
    type("/a");
    await flush(200);
    type("/ab");
    await flush(300);
    expect(check).toHaveBeenCalledTimes(1);
    expect(check.mock.calls[0]![0].path).toBe("/ab");
  });
  it("blur는 즉시 확인한다", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    render(<Harness check={check} />);
    type("/srv/app");
    fireEvent.blur(input());
    await flush(0);
    expect(check).toHaveBeenCalledTimes(1);
  });
  it("붙여넣기는 즉시 확인한다", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    render(<Harness check={check} />);
    fireEvent.paste(input());
    type("/srv/pasted");
    await flush(0);
    expect(check).toHaveBeenCalledTimes(1);
  });
  it("Enter는 즉시 확인하고, 이미 ok면 제출한다. IME 조합 중 Enter는 무시한다", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    const onSubmit = vi.fn();
    render(<Harness check={check} onSubmit={onSubmit} />);
    type("/srv/app");
    fireEvent.keyDown(input(), { key: "Enter", isComposing: true, keyCode: 229 });
    await flush(0);
    expect(check).not.toHaveBeenCalled();
    fireEvent.keyDown(input(), { key: "Enter" });
    await flush(0);
    expect(check).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
  it("오래된 응답은 버린다", async () => {
    const resolvers: Record<string, (o: FolderCheckOutcome) => void> = {};
    const check: FolderCheckFn = (r) => new Promise((res) => { resolvers[r.path] = res; });
    render(<Harness check={check} />);
    type("/slow");
    fireEvent.blur(input());
    await flush(0);
    type("/fast");
    fireEvent.blur(input());
    await flush(0);
    await act(async () => {
      resolvers["/fast"]!(checked({ path: "/fast" }));
      resolvers["/slow"]!(checked({ path: "/slow", exists: false, is_dir: false, readable: false, can_create: false }));
    });
    expect(result().getAttribute("data-state")).toBe("ok");
    expect(result().textContent).toContain("/fast");
  });
  it("입력을 비우면 idle", async () => {
    render(<Harness check={async () => checked()} initial="/srv/app" />);
    await flush(0);
    expect(result().getAttribute("data-state")).toBe("ok");
    type("");
    expect(result().getAttribute("data-state")).toBe("idle");
  });
  it("확인 중 표시는 150ms 넘을 때만", async () => {
    render(<Harness check={() => new Promise(() => undefined)} />);
    type("/x");
    fireEvent.blur(input());
    await flush(0);
    expect(result().getAttribute("data-state")).toBe("idle");
    await flush(150);
    expect(result().getAttribute("data-state")).toBe("checking");
    expect(result().textContent).toContain("확인하는 중");
  });
  it("check가 실패하면 error + 다시 확인", async () => {
    let fail = true;
    const check = vi.fn<FolderCheckFn>(async () => {
      if (fail) throw new Error("boom");
      return checked();
    });
    render(<Harness check={check} initial="/srv/app" />);
    await flush(0);
    expect(result().getAttribute("data-state")).toBe("error");
    expect(input().getAttribute("aria-invalid")).toBe("true");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "다시 확인" }));
    await flush(0);
    expect(result().getAttribute("data-state")).toBe("ok");
  });
});

describe("상태별 렌더", () => {
  const cases: { name: string; outcome: FolderCheckOutcome; state: string; group: string; text: RegExp; submittable: boolean }[] = [
    { name: "ok", outcome: checked({ path: "/srv/app" }), state: "ok", group: "ok", text: /사용할 수 있는 폴더/, submittable: true },
    { name: "ok_readonly", outcome: checked({ writable: false }), state: "ok_readonly", group: "ok", text: /쓰기 권한이 없습니다/, submittable: true },
    { name: "missing", outcome: checked({ exists: false, is_dir: false, readable: false, can_create: true }), state: "missing", group: "missing", text: /폴더가 없습니다/, submittable: false },
    { name: "missing_parent", outcome: checked({ exists: false, is_dir: false, readable: false }), state: "missing_parent", group: "blocked", text: /상위 폴더가 없어/, submittable: false },
    { name: "not_directory", outcome: checked({ is_dir: false }), state: "not_directory", group: "blocked", text: /파일입니다/, submittable: false },
    { name: "no_access", outcome: checked({ readable: false }), state: "no_access", group: "blocked", text: /읽을 수 없습니다/, submittable: false },
    { name: "invalid", outcome: checked({ path: null, problem: "relative" }), state: "invalid", group: "blocked", text: /절대 경로/, submittable: false },
    { name: "taken", outcome: { kind: "taken", projectId: "p1", name: "결제" }, state: "taken", group: "conflict", text: /‘결제’ 프로젝트로 등록/, submittable: false },
    { name: "taken_archived", outcome: { kind: "taken", projectId: "p1", name: "결제", archived: true }, state: "taken_archived", group: "conflict", text: /등록했다가 해제/, submittable: true },
    { name: "overlap_parent", outcome: { kind: "overlap", relation: "parent", projectId: "p2", name: "상위", path: "/srv" }, state: "overlap_parent", group: "conflict", text: /포함하는 ‘상위’/, submittable: false },
    { name: "overlap_child", outcome: { kind: "overlap", relation: "child", projectId: "p3", name: "하위", path: "/srv/app/x" }, state: "overlap_child", group: "conflict", text: /안에 이미 등록된 ‘하위’/, submittable: false },
    { name: "remote_disabled", outcome: { kind: "remote_disabled" }, state: "remote_disabled", group: "blocked", text: /밖에서 접속/, submittable: true },
  ];
  it.each(cases)("$name", async ({ outcome, state, group, text, submittable }) => {
    const onStateChange = vi.fn();
    render(<Harness check={async () => outcome} initial="/srv/app" onStateChange={onStateChange} />);
    await flush(0);
    expect(result().getAttribute("data-state")).toBe(state);
    expect(result().getAttribute("data-group")).toBe(group);
    expect(result().textContent).toMatch(text);
    expect(onStateChange.mock.lastCall![0].submittable).toBe(submittable);
    expect(result().getAttribute("role")).toBe("status");
    expect(result().getAttribute("aria-live")).toBe("polite");
    expect(input().getAttribute("aria-describedby")).toContain("fp-result");
  });
  it("저장될 경로가 입력과 다르면 줄이 추가된다", async () => {
    render(<Harness check={async () => checked({ path: "/real/app", input: "/link/app", link: true })} initial="/link/app" />);
    await flush(0);
    expect(result().textContent).toContain("입력한 경로는 /real/app로 저장됩니다.");
  });
  it("겹침: 이유 한 줄과 [그 프로젝트 열기]", async () => {
    const onOpen = vi.fn();
    render(<Harness check={async () => ({ kind: "overlap", relation: "parent", projectId: "p2", name: "상위", path: "/srv" })} initial="/srv/app" onOpenProject={onOpen} />);
    await flush(0);
    expect(result().textContent).toContain("로그·실행 기록이 섞이기");
    fireEvent.click(screen.getByRole("button", { name: "그 프로젝트 열기" }));
    expect(onOpen).toHaveBeenCalledWith("p2");
  });
  it("missing: 누를 때만 create: true로 요청하고 성공하면 ok", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => (r.create ? checked({ path: r.path }) : checked({ path: r.path, exists: false, is_dir: false, readable: false, can_create: true })));
    render(<Harness check={check} initial="/srv/new" />);
    await flush(0);
    expect(check.mock.calls.every((c) => !c[0].create)).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "이 경로에 폴더 만들기" }));
    await flush(0);
    expect(check.mock.lastCall![0]).toEqual({ path: "/srv/new", create: true });
    expect(result().getAttribute("data-state")).toBe("ok");
  });
  it("경로 다시 지정: exclude_project_id를 싣고, 이전 경로와 같으면 same_path", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    render(<Harness check={check} initial="/srv/old" excludeProjectId="p9" currentFolder="/srv/old" />);
    await flush(0);
    expect(check.mock.calls[0]![0].excludeProjectId).toBe("p9");
    expect(result().getAttribute("data-state")).toBe("same_path");
  });
  it("add 모드는 excludeProjectId를 보내지 않는다", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    render(<Harness check={check} initial="/srv/x" />);
    await flush(0);
    expect("excludeProjectId" in check.mock.calls[0]![0]).toBe(false);
  });
  it("결과 영역은 어떤 상태에서도 존재하고 min-height 44px 규칙이 있다", async () => {
    const { readFileSync } = await import("node:fs");
    const css = readFileSync(`${__dirname}/styles.css`, "utf-8");
    expect(/\.ac-fp-result\s*\{[^}]*min-height:\s*44px/.test(css)).toBe(true);
    render(<Harness check={async () => checked()} />);
    expect(result()).toBeTruthy();
  });
});

describe("찾아보기 패널", () => {
  const list: FolderListFn = async (r) => {
    if (r.path === "/srv") {
      return sampleListing("/srv", [
        { name: "app", path: "/srv/app" },
        { name: "docs", path: "/srv/docs", project_id: "p1", project_name: "문서" },
        { name: "secret", path: "/srv/secret", locked: true },
        { name: ".cache", path: "/srv/.cache", hidden: true },
        { name: "lnk", path: "/srv/lnk", link: true },
      ].filter((e) => r.hidden || !e.hidden));
    }
    return sampleListing(r.path, []);
  };
  async function open(check: FolderCheckFn, extra: Partial<FolderPickerProps> = {}, initial = "/srv") {
    render(<Harness check={check} list={list} initial={initial} {...extra} />);
    await flush(0);
    fireEvent.click(screen.getByRole("button", { name: /폴더 선택…$/ }));
    await flush(0);
    await flush(0);
  }
  const listbox = () => screen.getByRole("listbox", { name: "폴더 목록" });

  it("입력 경로에서 열리고 항목 표시(등록됨 칩, 잠금, 링크)를 그린다", async () => {
    await open(async (r) => checked({ path: r.path }));
    expect(screen.getByRole("button", { name: /폴더 선택…$/ }).getAttribute("aria-expanded")).toBe("true");
    const opts = within(listbox()).getAllByRole("option");
    expect(opts.map((o) => o.querySelector(".ac-fp-name")!.textContent)).toEqual(["app", "docs", "secret", "lnk"]);
    expect(opts[1]!.textContent).toContain("등록됨: 문서");
    expect(opts[2]!.getAttribute("aria-disabled")).toBe("true");
    expect(opts[3]!.textContent).toContain("링크");
    expect(opts[0]!.getAttribute("aria-setsize")).toBe("4");
    expect(opts[0]!.getAttribute("aria-posinset")).toBe("1");
  });
  it("숨김 폴더 토글", async () => {
    await open(async (r) => checked({ path: r.path }));
    fireEvent.click(screen.getByLabelText("숨김 폴더 보기"));
    await flush(0);
    expect(within(listbox()).getAllByRole("option")).toHaveLength(5);
  });
  it("키보드: 방향키·Home/End로 이동, Enter로 들어가면 입력이 바뀌고 바로 확인된다", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    await open(check);
    const lb = listbox();
    const activeName = () => document.getElementById(lb.getAttribute("aria-activedescendant")!)!.querySelector(".ac-fp-name")!.textContent;
    expect(activeName()).toBe("app");
    fireEvent.keyDown(lb, { key: "ArrowDown" });
    expect(activeName()).toBe("docs");
    fireEvent.keyDown(lb, { key: "End" });
    expect(activeName()).toBe("lnk");
    fireEvent.keyDown(lb, { key: "Home" });
    expect(activeName()).toBe("app");
    const calls = check.mock.calls.length;
    fireEvent.keyDown(lb, { key: "Enter" });
    await flush(0);
    expect(input().value).toBe("/srv/app");
    expect(check.mock.calls.length).toBeGreaterThan(calls);
    expect(check.mock.lastCall![0].path).toBe("/srv/app");
  });
  it("type-ahead", async () => {
    await open(async (r) => checked({ path: r.path }));
    const lb = listbox();
    fireEvent.keyDown(lb, { key: "l" });
    expect(document.getElementById(lb.getAttribute("aria-activedescendant")!)!.textContent).toContain("lnk");
  });
  it("잠긴 폴더는 들어갈 수 없다", async () => {
    await open(async (r) => checked({ path: r.path }));
    const lb = listbox();
    fireEvent.keyDown(lb, { key: "ArrowDown" });
    fireEvent.keyDown(lb, { key: "ArrowDown" });
    fireEvent.keyDown(lb, { key: "Enter" });
    await flush(0);
    expect(input().value).toBe("/srv");
  });
  it("← 로 상위, 상위가 없으면 시작 위치", async () => {
    const onList = vi.fn(list);
    await open(async (r) => checked({ path: r.path }), { list: onList });
    fireEvent.keyDown(listbox(), { key: "ArrowLeft" });
    await flush(0);
    expect(onList.mock.lastCall![0].path).toBe("/");
    expect(input().value).toBe("/");
  });
  it("빵부스러기: nav + ol, 현재 조각 aria-current", async () => {
    await open(async (r) => checked({ path: r.path }));
    const nav = screen.getByRole("navigation", { name: "경로" });
    expect(nav.querySelector("ol")).toBeTruthy();
    expect(nav.querySelector('[aria-current="location"]')!.textContent).toBe("srv");
  });
  it("Esc는 패널만 접고 버튼으로 돌아간다", async () => {
    await open(async (r) => checked({ path: r.path }));
    fireEvent.keyDown(listbox(), { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /폴더 선택…$/ }));
  });
  it("[이 폴더 선택]은 패널을 접고 onPicked를 부른다", async () => {
    const onPicked = vi.fn();
    await open(async (r) => checked({ path: r.path }), { onPicked });
    fireEvent.click(screen.getByRole("button", { name: "이 폴더 선택" }));
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onPicked.mock.calls[0]![0]).toBe("/srv");
  });
  it("새 폴더: Enter로 만들고 그 안으로 들어간다. 잘못된 이름·서버 거절은 행 아래에 보인다", async () => {
    const createFolder = vi.fn(async (r: { parent: string; name: string }) => (r.name === "dup" ? { ok: false as const, code: "exists" } : { ok: true as const, path: `${r.parent}/${r.name}` }));
    await open(async (r) => checked({ path: r.path }), { createFolder });
    fireEvent.click(screen.getByRole("button", { name: "새 폴더" }));
    const name = screen.getByLabelText("새 폴더 이름");
    fireEvent.change(name, { target: { value: "a/b" } });
    fireEvent.keyDown(name, { key: "Enter" });
    expect(screen.getByRole("alert").textContent).toContain("쓸 수 없는 글자");
    fireEvent.change(name, { target: { value: "dup" } });
    fireEvent.keyDown(name, { key: "Enter" });
    await flush(0);
    expect(screen.getByRole("alert").textContent).toContain("이미 있는 이름");
    fireEvent.change(name, { target: { value: "fresh" } });
    fireEvent.keyDown(name, { key: "Enter" });
    await flush(0);
    expect(createFolder).toHaveBeenLastCalledWith({ parent: "/srv", name: "fresh" }, expect.anything());
    expect(input().value).toBe("/srv/fresh");
    expect(screen.queryByLabelText("새 폴더 이름")).toBeNull();
  });
  it("새 폴더 Esc는 입력 행만 닫는다", async () => {
    await open(async (r) => checked({ path: r.path }), { createFolder: async () => ({ ok: false, code: "x" }) });
    fireEvent.click(screen.getByRole("button", { name: "새 폴더" }));
    fireEvent.keyDown(screen.getByLabelText("새 폴더 이름"), { key: "Escape" });
    expect(screen.queryByLabelText("새 폴더 이름")).toBeNull();
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
  it("빈 폴더 / 오류 + 다시 시도 / 잘림", async () => {
    let mode: "empty" | "error" | "trunc" = "empty";
    const l: FolderListFn = async (r) => {
      if (mode === "error") throw new Error("x");
      return sampleListing(r.path, mode === "empty" ? [] : sampleEntries(3, r.path), { truncated: mode === "trunc" });
    };
    await open(async (r) => checked({ path: r.path }), { list: l });
    expect(screen.getByText("하위 폴더가 없습니다")).toBeTruthy();
    cleanup();
    mode = "error";
    await open(async (r) => checked({ path: r.path }), { list: l });
    expect(screen.getByText("폴더 목록을 불러오지 못했습니다")).toBeTruthy();
    mode = "trunc";
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await flush(0);
    expect(screen.getByText(/앞의 3개만 보입니다/)).toBeTruthy();
  });
  it("2000항목은 일부만 DOM에 그리고 aria-setsize는 2000", async () => {
    const big: FolderListFn = async (r) => sampleListing(r.path, sampleEntries(2000, r.path));
    await open(async (r) => checked({ path: r.path }), { list: big });
    const opts = within(listbox()).getAllByRole("option");
    expect(opts.length).toBeGreaterThan(5);
    expect(opts.length).toBeLessThan(100);
    expect(opts[0]!.getAttribute("aria-setsize")).toBe("2000");
  });
  it("시작 위치: 입력 경로가 없으면 nearest_existing에서 시작하고 안내 줄을 보인다. 폴더로 들어가면 사라진다", async () => {
    const onList = vi.fn(list);
    await open(async (r) => checked({ path: r.path, exists: false, is_dir: false, readable: false, can_create: true, nearest_existing: "/srv" }), { list: onList }, "/srv/not/there");
    expect(onList.mock.calls[0]![0].path).toBe("/srv");
    expect(screen.getByText(/가장 가까운 상위 폴더\(\/srv\)/)).toBeTruthy();
    fireEvent.keyDown(listbox(), { key: "Enter" });
    await flush(0);
    expect(screen.queryByText(/가장 가까운 상위 폴더/)).toBeNull();
  });
  it("시작 위치: nearest_existing이 null이면 시작 위치(roots)에서 시작", async () => {
    const onList = vi.fn(list);
    await open(async (r) => checked({ path: r.path, exists: false, is_dir: false, readable: false, nearest_existing: null }), { list: onList }, "/nowhere");
    expect(onList).not.toHaveBeenCalled();
    expect(within(listbox()).getAllByRole("option").map((o) => o.textContent)).toEqual(["홈", "루트"]);
  });
  it("경로 다시 지정: 입력이 비면 이전 경로 기준(exclude_project_id 포함)", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path, exists: false, is_dir: false, readable: false, nearest_existing: "/srv" }));
    const onList = vi.fn(list);
    await open(check, { list: onList, currentFolder: "/srv/gone", excludeProjectId: "p9" }, "");
    expect(check.mock.lastCall![0]).toEqual({ path: "/srv/gone", excludeProjectId: "p9" });
    expect(onList.mock.calls[0]![0].path).toBe("/srv");
  });
  it("remote_disabled면 찾아보기를 막는다", async () => {
    render(<Harness check={async () => ({ kind: "remote_disabled" })} initial="/srv" />);
    await flush(0);
    const btn = screen.getByRole("button", { name: /폴더 선택…$/ });
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(btn);
    await flush(0);
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
