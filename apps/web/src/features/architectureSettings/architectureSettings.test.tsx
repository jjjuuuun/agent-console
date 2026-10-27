import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ArchitectureProfileList, Issue, ModuleInfo } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { ProfileEditor } from "./ProfileEditor";
import { ArchitectureSettingsEditor } from "./ArchitectureSettingsEditor";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { QueryClientProvider } from "@tanstack/react-query";
import "./index";

afterEach(cleanup);
const LONG = { timeout: 15_000 };

// 프로필 id·제목·출처는 이 테스트 안의 임의 값이다.
const mod = (id: string, roles: string[]): ModuleInfo => ({ id, kind: "k", version: "1.0.0", status: "active", web_roles: roles, provides: [] });
const profileList: ArchitectureProfileList = {
  profiles: [
    { id: "p-base", title: "기본 하나", origin: "default", issues: 0, cells: 4, edges: 3 },
    { id: "p-mine", title: "내 것", origin: "user", issues: 2, cells: 1, edges: 0 },
  ],
  default_profile: "p-base",
  include_defaults: true,
};
const issue = (severity: Issue["severity"], message: string, path?: string): Issue => ({ severity, code: "x", message, ...(path ? { path } : {}) });

describe("ProfileEditor: 저장 전 검사", () => {
  const body = (check: () => Promise<{ issues: Issue[] }>, over: Partial<Parameters<typeof ProfileEditor>[0]> = {}) => (
    <ProfileEditor id="p1" title="프로필" initialText={"title: 가\n"} readOnly={false} check={check} onSave={() => undefined} onClose={() => undefined} delayMs={0} {...over} />
  );

  it("검사 오류가 있으면 저장 버튼이 꺼지고 문제 목록이 보인다", async () => {
    const check = vi.fn(async () => ({ issues: [issue("error", "없는 칸을 가리키는 연결", "cells.foo"), issue("warning", "모르는 연산자", "edges[3].when")] }));
    render(body(check));
    const items = await screen.findAllByRole("listitem", {}, LONG);
    expect(items).toHaveLength(2);
    expect(screen.getByText("없는 칸을 가리키는 연결")).toBeTruthy();
    expect((screen.getByRole("button", { name: "프로필 저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect(check).toHaveBeenCalledWith({ id: "p1", profile: { title: "가" } });
  });

  it("경고만 있거나 문제가 없으면 저장할 수 있고, 저장하면 파싱한 본문을 넘긴다", async () => {
    const onSave = vi.fn();
    render(body(async () => ({ issues: [issue("warning", "경고만")] }), { onSave }));
    await screen.findByText("경고만", {}, LONG);
    const save = screen.getByRole("button", { name: "프로필 저장" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    expect(onSave).toHaveBeenCalledWith({ title: "가" });
  });

  it("YAML 형식 오류면 서버를 부르지 않고 저장이 꺼진다", async () => {
    const check = vi.fn(async () => ({ issues: [] }));
    render(body(check, { initialText: "a: [1\nb: 2" }));
    expect((await screen.findAllByText(/YAML 형식 오류/, {}, LONG)).length).toBeGreaterThan(0);
    expect((screen.getByRole("button", { name: "프로필 저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect(check).not.toHaveBeenCalled();
  });

  it("저장이 꺼진 이유가 포커스로 열리는 툴팁에 있다", async () => {
    render(body(vi.fn(async () => ({ issues: [] })), { initialText: "a: [1\nb: 2" }));
    const host = await screen.findByTestId("arch-save-reason", {}, LONG);
    expect(host.getAttribute("tabindex")).toBe("0");
    expect(host.getAttribute("aria-label")).toContain("YAML 형식 오류");
  });

  it("검사 요청이 실패하면 저장을 막지 않고 다시 시도 단추를 보인다", async () => {
    render(body(async () => { throw new Error("x"); }));
    expect(await screen.findByText(/검사하지 못했습니다/, {}, LONG)).toBeTruthy();
    expect((screen.getByRole("button", { name: "프로필 저장" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy();
  });
});

describe("설정 › 구조도 섹션", () => {
  const mount = (modules: ModuleInfo[], settings = {}) => {
    const { clients, rest } = createFakeClients({
      listModules: vi.fn(async () => modules),
      getSettingsVersioned: vi.fn(async () => ({ value: settings, version_hash: "s1" })),
      listArchitectureProfiles: vi.fn(async () => profileList),
      checkArchitectureProfile: vi.fn(async () => ({ issues: [] })),
      getArchitectureProfile: vi.fn(async () => ({ ...profileList.profiles![0], profile: { title: "기본 하나" }, problems: [] })),
    });
    mountApp(clients, "/settings#architecture");
    return rest;
  };

  it("구조도 모듈이 없으면 섹션이 없다", async () => {
    mount([mod("m-s", ["settings"])]);
    await screen.findByRole("navigation", { name: /섹션/ }, LONG);
    await waitFor(() => expect(screen.getByRole("link", { name: /채팅/ })).toBeTruthy(), LONG);
    expect(screen.queryByRole("link", { name: /구조도/ })).toBeNull();
    expect(screen.queryByTestId("arch-settings")).toBeNull();
  });

  it("모듈이 있으면 프로필 목록(출처 배지·문제 수)이 보이고, 기본 프로필 사용을 끄면 저장 값이 바뀐다", async () => {
    const rest = mount([mod("m-s", ["settings"]), mod("m-a", ["architecture"])], { architecture: { profiles: { "p-mine": { title: "내 것" } } } });
    expect(await screen.findByTestId("arch-settings", {}, LONG)).toBeTruthy();
    const base = (await screen.findByText("기본 하나", {}, LONG)).closest("li") as HTMLElement;
    expect(within(base).getByText("기본")).toBeTruthy();
    expect(within(base).getByText("문제 없음")).toBeTruthy();
    const mine = screen.getByText("내 것", { selector: ".arch-settings-row-title" }).closest("li") as HTMLElement;
    expect(within(mine).getByText("사용자")).toBeTruthy();
    expect(within(mine).getByText("문제 2")).toBeTruthy();
    const sw = screen.getByRole("switch", { name: /기본 프로필 사용/ });
    expect(sw.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(sw);
    expect(sw.getAttribute("aria-checked")).toBe("false");
    // 초안에서 바로 기본 출처 행이 빠진다
    await waitFor(() => expect(screen.queryByText("기본 하나", { selector: ".arch-settings-row-title" })).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest["putSettingsVersioned"]).toHaveBeenCalled());
    const saved = (rest["putSettingsVersioned"] as ReturnType<typeof vi.fn>).mock.calls[0]![0] as { architecture: { include_defaults: boolean; profiles: object } };
    expect(saved.architecture.include_defaults).toBe(false);
    expect(Object.keys(saved.architecture.profiles)).toEqual(["p-mine"]);
  });

  it("기본 프로필 끄기는 null로 기록하고 [다시 켜기]로 되돌린다", async () => {
    mount([mod("m-s", ["settings"]), mod("m-a", ["architecture"])]);
    const base = (await screen.findByText("기본 하나", {}, LONG)).closest("li") as HTMLElement;
    fireEvent.click(within(base).getByRole("button", { name: "끄기" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /끈 프로필 1/ })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /끈 프로필 1/ }));
    fireEvent.click(screen.getByRole("button", { name: "다시 켜기" }));
    await waitFor(() => expect(screen.getByText("기본 하나", { selector: ".arch-settings-row-title" })).toBeTruthy());
  });
});

describe("ArchitectureSettingsEditor", () => {
  it("열기만 해서는 값을 바꾸지 않는다(폼이 채운 스키마 기본값은 걷는다)", async () => {
    const { clients } = createFakeClients({ listArchitectureProfiles: vi.fn(async () => ({ profiles: [], default_profile: null, include_defaults: true })) });
    const onChange = vi.fn();
    const v = { profiles: { "p-x": { title: "t" } } };
    render(
      <ApiProvider clients={clients}>
        <QueryClientProvider client={createAppQueryClient({ retry: false })}>
          <ArchitectureSettingsEditor value={v} saved={v} onChange={onChange} />
        </QueryClientProvider>
      </ApiProvider>,
    );
    await screen.findByTestId("arch-settings", {}, LONG);
    await new Promise((r) => setTimeout(r, 300));
    expect(onChange).not.toHaveBeenCalled();
  }, 30_000);
});
