import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { useState, type ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FolderPicker, type FolderPickerProps } from "./FolderPicker";
import { checked, sampleEntries, sampleListing } from "./testing";
import type { FolderCheckFn, FolderListFn, FolderPickFn, FolderPickOutcome } from "./types";

const ROOTS = [{ kind: "home", path: "/home/me", label: "홈" }];
const list: FolderListFn = async (r) => sampleListing(r.path, sampleEntries(3, r.path));

function Harness(p: Partial<FolderPickerProps> & { initial?: string }): ReactElement {
  const [v, setV] = useState(p.initial ?? "");
  const check: FolderCheckFn = p.check ?? (async (r) => checked({ path: r.path }));
  return <FolderPicker id="fp" roots={ROOTS} list={list} {...p} check={check} value={v} onValueChange={setV} />;
}

const flush = async (ms = 0) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};
const pickBtn = () => screen.getByRole("button", { name: /^(폴더 선택…|다른 폴더 선택…|폴더 선택 창에서 고르세요…)$/ });
const click = async (el: HTMLElement) => {
  fireEvent.click(el);
  await flush(0);
  await flush(0);
};
const result = () => document.getElementById("fp-result")!;
const status = () => document.getElementById("fp-pick-status")!;

/** 사용자가 고를 때까지 열려 있는 가짜 OS 선택 창. */
function deferredPick() {
  let resolve: (o: FolderPickOutcome) => void = () => undefined;
  let reject: (e: unknown) => void = () => undefined;
  let signal: AbortSignal | undefined;
  const fn = vi.fn<FolderPickFn>((_initial, s) => {
    signal = s;
    return new Promise<FolderPickOutcome>((res, rej) => {
      resolve = res;
      reject = rej;
    });
  });
  return { fn, resolve: (o: FolderPickOutcome) => resolve(o), reject: (e: unknown) => reject(e), signal: () => signal };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("선택 우선 배치 · 포커스 순서", () => {
  it("[폴더 선택…]이 첫 포커스이자 문서에서 첫 버튼이다. 직접 입력은 접혀 있고 입력 칸이 없다", () => {
    render(<Harness autoFocus />);
    expect(document.activeElement).toBe(pickBtn());
    expect(screen.getAllByRole("button")[0]).toBe(pickBtn());
    expect(pickBtn().getAttribute("data-variant")).toBe("primary");
    const disclosure = screen.getByRole("button", { name: "경로를 직접 입력" });
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByLabelText("폴더 경로")).toBeNull();
    expect(screen.getByText("선택한 폴더가 여기에 표시됩니다")).toBeTruthy();
  });
  it("pickRef로 버튼을 받는다", () => {
    let el: HTMLButtonElement | null = null;
    render(<Harness pickRef={(n) => { el = n; }} />);
    expect(el).toBe(pickBtn());
  });
  it("직접 입력을 펼치면 칸이 나타나고, 타이핑은 300ms 디바운스한다", async () => {
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    render(<Harness check={check} />);
    fireEvent.click(screen.getByRole("button", { name: "경로를 직접 입력" }));
    const input = screen.getByLabelText("폴더 경로");
    fireEvent.change(input, { target: { value: "/srv/app" } });
    await flush(299);
    expect(check).not.toHaveBeenCalled();
    await flush(1);
    expect(check).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("group", { name: "프로젝트 폴더" }).textContent).toContain("/srv/app");
  });
  it("선택 뒤에는 [다른 폴더 선택…]이 되고 선택한 경로와 [복사]가 보인다", async () => {
    const write = vi.fn();
    render(<Harness initial="/srv/app" copy={write} />);
    await flush(0);
    expect(pickBtn().textContent).toBe("다른 폴더 선택…");
    expect(pickBtn().getAttribute("data-variant")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "경로 복사" }));
    expect(write).toHaveBeenCalledWith("/srv/app");
  });
});

describe("방식 분기", () => {
  it("onPickNative가 없으면 같은 버튼이 찾아보기 패널을 연다", async () => {
    render(<Harness initial="/srv" />);
    await flush(0);
    await click(pickBtn());
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(pickBtn().getAttribute("aria-expanded")).toBe("true");
  });
  it("native_dialog: false면 선택 창을 부르지 않고 패널을 연다", async () => {
    const pick = deferredPick();
    render(<Harness initial="/srv" onPickNative={pick.fn} capabilities={{ browse: true, native_dialog: false }} />);
    await flush(0);
    await click(pickBtn());
    expect(pick.fn).not.toHaveBeenCalled();
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(status().textContent).toBe("");
  });
  it("browse: false면 버튼이 aria-disabled이고 직접 입력이 자동으로 열린다", async () => {
    render(<Harness capabilities={{ browse: false, native_dialog: false }} onPickNative={deferredPick().fn} />);
    expect(pickBtn().getAttribute("aria-disabled")).toBe("true");
    expect(pickBtn().title).toContain("밖에서 접속");
    expect(screen.getByLabelText("폴더 경로")).toBeTruthy();
    await click(pickBtn());
    expect(screen.queryByRole("listbox")).toBeNull();
  });
  it("capabilities를 아직 모르면(null) 선택 창을 먼저 시도한다", async () => {
    const pick = deferredPick();
    render(<Harness capabilities={null} onPickNative={pick.fn} />);
    await click(pickBtn());
    expect(pick.fn).toHaveBeenCalledTimes(1);
  });
});

describe("선택 흐름 상태", () => {
  const native = { browse: true, native_dialog: true };

  it("대기: 버튼 라벨·aria-disabled·[선택 취소]·창 안내가 보이고 입력이 막힌다. initial은 선택한 경로", async () => {
    const pick = deferredPick();
    const onPhase = vi.fn();
    render(<Harness initial="/srv/app" capabilities={native} onPickNative={pick.fn} defaultManualOpen onSelectPhaseChange={onPhase} />);
    await flush(0);
    await click(pickBtn());
    expect(pick.fn.mock.calls[0]![0]).toBe("/srv/app");
    expect(pickBtn().textContent).toBe("폴더 선택 창에서 고르세요…");
    expect(pickBtn().getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("button", { name: "선택 취소" })).toBeTruthy();
    expect(status().textContent).toContain("창이 보이지 않으면");
    expect(status().getAttribute("role")).toBe("status");
    expect((screen.getByLabelText("폴더 경로") as HTMLInputElement).disabled).toBe(true);
    expect(onPhase).toHaveBeenLastCalledWith("waiting");
    // 대기 중 다시 눌러도 요청은 하나
    await click(pickBtn());
    expect(pick.fn).toHaveBeenCalledTimes(1);
  });
  it("picked(check 없음): 값이 바뀌고 디바운스 없이 즉시 확인하며 onPicked를 부른다", async () => {
    const pick = deferredPick();
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    const onPicked = vi.fn();
    render(<Harness check={check} capabilities={native} onPickNative={pick.fn} onPicked={onPicked} />);
    await click(pickBtn());
    await act(async () => pick.resolve({ status: "picked", path: "/srv/chosen" }));
    await flush(0);
    expect(check).toHaveBeenCalledTimes(1);
    expect(check.mock.calls[0]![0]).toEqual({ path: "/srv/chosen" });
    expect(result().getAttribute("data-state")).toBe("ok");
    expect(screen.getByRole("group", { name: "프로젝트 폴더" }).textContent).toContain("/srv/chosen");
    expect(onPicked).toHaveBeenCalledTimes(1);
    expect(onPicked.mock.calls[0]![0]).toBe("/srv/chosen");
    expect(onPicked.mock.calls[0]![1].id).toBe("ok");
    expect(document.activeElement).toBe(pickBtn());
    expect(pickBtn().textContent).toBe("다른 폴더 선택…");
  });
  it("picked(check 있음): 다시 요청하지 않고 그대로 쓴다. 충돌을 담은 outcome이 우선한다", async () => {
    const pick = deferredPick();
    const check = vi.fn<FolderCheckFn>(async (r) => checked({ path: r.path }));
    render(<Harness check={check} capabilities={native} onPickNative={pick.fn} />);
    await click(pickBtn());
    await act(async () => pick.resolve({ status: "picked", path: "/srv/chosen", check: { input: "/srv/chosen", path: "/srv/chosen", exists: true, is_dir: true, readable: true, writable: false, can_create: false } }));
    await flush(0);
    expect(check).not.toHaveBeenCalled();
    expect(result().getAttribute("data-state")).toBe("ok_readonly");
    await click(pickBtn());
    await act(async () => pick.resolve({ status: "picked", path: "/srv/taken", outcome: { kind: "taken", projectId: "p1", name: "결제" } }));
    await flush(0);
    expect(check).not.toHaveBeenCalled();
    expect(result().getAttribute("data-state")).toBe("taken");
  });
  it("picked인데 경로가 없으면 failed로 다룬다", async () => {
    const pick = deferredPick();
    render(<Harness capabilities={native} onPickNative={pick.fn} />);
    await click(pickBtn());
    await act(async () => pick.resolve({ status: "picked" }));
    await flush(0);
    expect(status().getAttribute("data-phase")).toBe("failed");
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
  it("cancelled(결과): 오류가 아니다. 이전 선택을 유지하고 3초 뒤 안내가 사라진다. 포커스는 버튼으로", async () => {
    const pick = deferredPick();
    render(<Harness initial="/srv/app" capabilities={native} onPickNative={pick.fn} />);
    await flush(0);
    await click(pickBtn());
    await act(async () => pick.resolve({ status: "cancelled" }));
    await flush(0);
    expect(status().textContent).toBe("선택을 취소했습니다");
    expect(status().getAttribute("data-tone")).toBeNull();
    expect(screen.getByRole("group", { name: "프로젝트 폴더" }).textContent).toContain("/srv/app");
    expect(document.activeElement).toBe(pickBtn());
    expect(pickBtn().getAttribute("aria-disabled")).toBeNull();
    await flush(3000);
    expect(status().textContent).toBe("");
  });
  it("[선택 취소]: 요청을 abort하고, 늦게 온 결과는 버린다", async () => {
    const pick = deferredPick();
    render(<Harness capabilities={native} onPickNative={pick.fn} />);
    await click(pickBtn());
    expect(pick.signal()!.aborted).toBe(false);
    await click(screen.getByRole("button", { name: "선택 취소" }));
    expect(pick.signal()!.aborted).toBe(true);
    expect(status().getAttribute("data-phase")).toBe("cancelled");
    await act(async () => pick.resolve({ status: "picked", path: "/late" }));
    await flush(0);
    expect(screen.getByRole("group", { name: "프로젝트 폴더" }).textContent).not.toContain("/late");
    expect(screen.queryByRole("button", { name: "선택 취소" })).toBeNull();
  });
  it("대기 중 Esc는 대화상자(상위 핸들러)가 아니라 선택을 취소한다. 대기가 아니면 Esc는 상위로 올라간다", async () => {
    const pick = deferredPick();
    const outer = vi.fn();
    render(
      <div onKeyDown={(e) => outer(e.key)}>
        <Harness capabilities={native} onPickNative={pick.fn} />
      </div>,
    );
    await click(pickBtn());
    fireEvent.keyDown(pickBtn(), { key: "Escape" });
    expect(outer).not.toHaveBeenCalled();
    expect(pick.signal()!.aborted).toBe(true);
    expect(status().getAttribute("data-phase")).toBe("cancelled");
    fireEvent.keyDown(pickBtn(), { key: "Escape" });
    expect(outer).toHaveBeenCalledWith("Escape");
  });
  it("대기 30초가 지나면 [앱 안에서 찾아보기]가 나타나고, 누르면 선택을 취소하고 패널을 연다", async () => {
    const pick = deferredPick();
    render(<Harness initial="/srv" capabilities={native} onPickNative={pick.fn} />);
    await flush(0);
    await click(pickBtn());
    expect(screen.queryByRole("button", { name: "앱 안에서 찾아보기" })).toBeNull();
    await flush(30000);
    await click(screen.getByRole("button", { name: "앱 안에서 찾아보기" }));
    expect(pick.signal()!.aborted).toBe(true);
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
  it("unavailable: 찾아보기 패널을 자동으로 열고 안내와 원인(자세히)을 보인다. 이후 같은 버튼은 곧바로 패널을 연다", async () => {
    const pick = deferredPick();
    render(<Harness initial="/srv" capabilities={native} onPickNative={pick.fn} />);
    await flush(0);
    await click(pickBtn());
    await act(async () => pick.resolve({ status: "unavailable", reason: "no display" }));
    await flush(0);
    await flush(0);
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(status().textContent).toContain("폴더 선택 창을 쓸 수 없어 앱 안 찾아보기를 엽니다");
    expect(status().getAttribute("data-tone")).toBe("info");
    expect(status().textContent).toContain("no display");
    // 패널을 접고 다시 누르면 선택 창을 다시 부르지 않는다
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    await click(pickBtn());
    expect(pick.fn).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
  it("failed(결과·그 밖의 모르는 값·reject): 패널을 자동으로 열고 danger 줄과 [다시 선택]", async () => {
    for (const how of ["status", "unknown", "reject"] as const) {
      cleanup();
      const pick = deferredPick();
      render(<Harness initial="/srv" capabilities={native} onPickNative={pick.fn} />);
      await flush(0);
      await click(pickBtn());
      await act(async () => (how === "reject" ? pick.reject(new Error("net")) : pick.resolve({ status: how === "status" ? "failed" : "weird" })));
      await flush(0);
      await flush(0);
      expect(status().getAttribute("data-phase"), how).toBe("failed");
      expect(status().getAttribute("data-tone"), how).toBe("danger");
      expect(status().textContent).toContain("폴더 선택 창을 열지 못했습니다");
      expect(screen.getByRole("listbox"), how).toBeTruthy();
      expect(screen.getByRole("button", { name: "다시 선택" })).toBeTruthy();
    }
  });
  it("busy·timeout: warning 줄 + [다시 선택] + [앱 안에서 찾아보기]. 패널은 자동으로 열지 않는다", async () => {
    for (const st of ["busy", "timeout"] as const) {
      cleanup();
      const pick = deferredPick();
      render(<Harness initial="/srv" capabilities={native} onPickNative={pick.fn} />);
      await flush(0);
      await click(pickBtn());
      await act(async () => pick.resolve({ status: st }));
      await flush(0);
      expect(status().getAttribute("data-tone")).toBe("warning");
      expect(status().textContent).toContain(st === "busy" ? "이미 열려 있습니다" : "선택 시간이 지나");
      expect(screen.queryByRole("listbox")).toBeNull();
      await click(screen.getByRole("button", { name: "다시 선택" }));
      expect(pick.fn).toHaveBeenCalledTimes(2);
      await act(async () => pick.resolve({ status: st }));
      await flush(0);
      await click(screen.getByRole("button", { name: "앱 안에서 찾아보기" }));
      expect(screen.getByRole("listbox")).toBeTruthy();
    }
  });
  it("컴포넌트가 사라지면 대기 중인 요청을 끊는다", async () => {
    const pick = deferredPick();
    const { unmount } = render(<Harness capabilities={native} onPickNative={pick.fn} />);
    await click(pickBtn());
    unmount();
    expect(pick.signal()!.aborted).toBe(true);
  });
});

describe("구성 폴더(configDir)와 기존 구성 안내", () => {
  it("configDir가 있으면 만들 폴더 한 줄을 보이고, 없으면 보이지 않는다", async () => {
    const { rerender } = render(<Harness initial="/srv/app" configDir=".cfg" />);
    await flush(0);
    const line = document.querySelector(".ac-fp-creates")!;
    expect(line.textContent).toContain(".cfg 폴더를 만들어");
    expect(line.querySelector("code")!.textContent).toBe(".cfg");
    rerender(<Harness initial="/srv/app" />);
    expect(document.querySelector(".ac-fp-creates")).toBeNull();
  });
  it("manifest_found: 안내 줄(이름·개수)을 보이고 만들 폴더 줄은 숨긴다. 필드가 없으면 안내가 없다", async () => {
    const withManifest = async () => checked({ path: "/srv/app", manifest: { name: "payments", count: 3 } });
    render(<Harness initial="/srv/app" configDir=".cfg" check={withManifest} />);
    await flush(0);
    expect(result().getAttribute("data-state")).toBe("manifest_found");
    expect(result().getAttribute("data-group")).toBe("ok");
    expect(result().textContent).toContain("이 폴더에 프로젝트 구성이 이미 있습니다: ‘payments’ · 구성 3개. 그대로 불러옵니다.");
    expect(document.querySelector(".ac-fp-creates")).toBeNull();
    cleanup();
    render(<Harness initial="/srv/app" configDir=".cfg" check={async () => checked({ path: "/srv/app" })} />);
    await flush(0);
    expect(result().getAttribute("data-state")).toBe("ok");
    expect(result().textContent).not.toContain("구성이 이미 있습니다");
  });
  it("manifest 이름·개수가 없어도 문장이 깨지지 않는다", async () => {
    render(<Harness initial="/srv/app" check={async () => checked({ path: "/srv/app", manifest: {} })} />);
    await flush(0);
    expect(result().textContent).toContain("이 폴더에 프로젝트 구성이 이미 있습니다. 그대로 불러옵니다.");
  });
  it("manifest.valid === false: warning, 추가는 막지 않는다", async () => {
    const onState = vi.fn();
    render(<Harness initial="/srv/app" onStateChange={onState} check={async () => checked({ path: "/srv/app", manifest: { valid: false } })} />);
    await flush(0);
    expect(result().getAttribute("data-state")).toBe("manifest_invalid");
    expect(result().textContent).toContain("프로젝트 설정 파일을 읽을 수 없습니다");
    expect(onState.mock.lastCall![0].submittable).toBe(true);
  });
  it("ok_readonly: configDir가 있으면 {dir} 문구(고정폭), 없으면 기존 문구. 만들 폴더 줄은 숨긴다", async () => {
    const ro = async () => checked({ path: "/srv/app", writable: false });
    render(<Harness initial="/srv/app" configDir=".cfg" check={ro} />);
    await flush(0);
    expect(result().querySelector("code")!.textContent).toBe(".cfg");
    expect(result().textContent).toContain("이 폴더에 .cfg 폴더를 만들 수 없어");
    expect(document.querySelector(".ac-fp-creates")).toBeNull();
    cleanup();
    render(<Harness initial="/srv/app" check={ro} />);
    await flush(0);
    expect(result().textContent).toContain("쓰기 권한이 없습니다");
  });
});

describe("접근성 (axe)", () => {
  const run = async (el: HTMLElement) => {
    const r = await axe.run(el, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`);
  };
  it("선택 전·대기·선택 뒤(직접 입력 펼침)·busy 상태에 위반이 없다", async () => {
    vi.useRealTimers();
    const pick = deferredPick();
    const { container } = render(<Harness capabilities={{ native_dialog: true }} onPickNative={pick.fn} configDir=".cfg" />);
    expect(await run(container)).toEqual([]);
    fireEvent.click(pickBtn());
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(await run(container)).toEqual([]);
    await act(async () => { pick.resolve({ status: "busy" }); await new Promise((r) => setTimeout(r, 20)); });
    expect(await run(container)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "경로를 직접 입력" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(await run(container)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "다시 선택" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    await act(async () => { pick.resolve({ status: "picked", path: "/srv/app", check: { input: "/srv/app", path: "/srv/app", exists: true, is_dir: true, readable: true, writable: true, can_create: false, manifest: { name: "a", count: 2 } } }); await new Promise((r) => setTimeout(r, 20)); });
    expect(result().getAttribute("data-state")).toBe("manifest_found");
    expect(await run(container)).toEqual([]);
  });
});
