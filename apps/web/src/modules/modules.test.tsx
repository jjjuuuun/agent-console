import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { ModuleInfo } from "@agent-console/contracts";
import { UnsavedGuard } from "../definition/unsaved";
import { createFakeClients } from "../testing/fakes";
import { mountApp } from "../testing/screenHarness";
import type { RouteDef } from "../shell/routeConfig";
import type { PageTable } from "../shell/routes";
import { LinkPart, type LinkPartDef } from "./index";

afterEach(cleanup);

// 임의의 가짜 모듈·역할·라우트: 실제 서버 모듈 이름에 기대지 않는다.
const mod = (id: string, status: string, roles: string[] = [], extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id, kind: "k-any", version: "0.0.1", status, web_roles: roles, ...extra });
const route = (id: string, path: string, titleKey: string, requires: string[], extra: Partial<RouteDef> = {}): RouteDef => ({ id, path, titleKey, icon: "x", badgeSource: null, gotoKey: null, position: "main", requires, ...extra });
const ROUTES: RouteDef[] = [
  route("r-a", "/a", "nav.chat", ["role-a"]),
  route("r-b", "/b", "nav.teams", ["role-b"]),
  route("r-c", "/c", "nav.agents", ["role-c"], { gotoKey: "x" }),
  route("r-s", "/s", "nav.settings", [], { serves: "settings", position: "bottom" }),
];
const nav = () => screen.getByRole("navigation", { name: "주 메뉴" });

describe("모듈 목록으로 화면 조립", () => {
  it("꺼진 모듈의 화면은 사이드바에서 빠지고, 주소로 들어가면 안내 화면이 나오며 주소는 그대로다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", "active", ["role-a"]), mod("m-2", "disabled", ["role-b"]), mod("m-3", "active", ["role-c"])]) });
    const view = mountApp(clients, "/b", { routes: ROUTES });
    expect(await screen.findByRole("heading", { name: "이 기능은 꺼져 있습니다", level: 1 })).toBeTruthy();
    expect(view.router.state.location.pathname).toBe("/b");
    const menu = nav();
    expect(within(menu).getByRole("link", { name: "채팅" })).toBeTruthy();
    expect(within(menu).getByRole("link", { name: "에이전트" })).toBeTruthy();
    expect(within(menu).queryByRole("link", { name: "팀 구성" })).toBeNull();
    // 필요한 기능: 역할 표시와 모듈 id·상태, 켜는 방법(꺼진 모듈 id가 끼워진 코드)
    expect(screen.getByText("role-b")).toBeTruthy();
    expect(screen.getByText("m-2")).toBeTruthy();
    expect(screen.getByLabelText("켜는 방법 (서버 설치자)").textContent).toContain("--enable-module m-2");
    expect(screen.getByRole("link", { name: "기능 목록 보기" }).getAttribute("href")).toBe("/s#modules");
  });

  it("같은 역할을 가진 모듈 중 하나만 켜져 있어도 화면이 열린다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", "disabled", ["role-a"]), mod("m-2", "active", ["role-a"]), mod("m-3", "failed", ["role-b"])]) });
    mountApp(clients, "/a", { routes: ROUTES });
    await waitFor(() => expect(within(nav()).getByRole("link", { name: "채팅" })).toBeTruthy());
    expect(within(nav()).queryByRole("link", { name: "팀 구성" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "이 기능은 꺼져 있습니다" })).toBeNull();
  });

  it("대표 상태에 따라 제목이 달라지고, 목록에 없는 항목은 설치 안내만 보인다(켜는 방법 상자 없음)", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", "failed", ["role-b"], { reason: "서버가 보낸 이유" })]) });
    mountApp(clients, "/b", { routes: ROUTES });
    expect(await screen.findByRole("heading", { name: "이 기능을 시작하지 못했습니다" })).toBeTruthy();
    expect(screen.getByText("서버가 보낸 이유")).toBeTruthy();
    expect(screen.queryByLabelText("켜는 방법 (서버 설치자)")).toBeNull();
    cleanup();
    const second = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", "active", ["role-a"])]) });
    mountApp(second.clients, "/b", { routes: ROUTES });
    expect(await screen.findByRole("heading", { name: "이 서버에는 이 기능이 설치되어 있지 않습니다" })).toBeTruthy();
    expect(screen.getByText("서버 목록에 없음")).toBeTruthy();
    expect(screen.queryByLabelText("켜는 방법 (서버 설치자)")).toBeNull();
    expect(screen.getByText(/설치되어 있지 않습니다\. 설치자에게/)).toBeTruthy();
  });

  it("목록을 받기 전에는 안내 화면을 먼저 그리지 않고, 받은 뒤에 결정한다", async () => {
    let resolve: (v: ModuleInfo[]) => void = () => {};
    const { clients } = createFakeClients({ listModules: vi.fn(() => new Promise<ModuleInfo[]>((r) => (resolve = r))) });
    mountApp(clients, "/b", { routes: ROUTES });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("heading", { name: /기능/ })).toBeNull();
    expect(screen.getByRole("status", { name: "메뉴를 불러오는 중" })).toBeTruthy();
    await act(async () => resolve([mod("m-1", "disabled", ["role-b"])]));
    expect(await screen.findByRole("heading", { name: "이 기능은 꺼져 있습니다" })).toBeTruthy();
  });

  it("모듈 목록 자체가 404이면 모든 화면을 켠 채로 둔다(옛 서버)", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => { throw new ApiError(404, { code: "not_found", message: "없음" }); }) });
    mountApp(clients, "/b", { routes: ROUTES });
    await waitFor(() => expect(within(nav()).getByRole("link", { name: "팀 구성" })).toBeTruthy());
    expect(within(nav()).getByRole("link", { name: "에이전트" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "이 기능은 꺼져 있습니다" })).toBeNull();
  });

  it("`/`는 켜진 첫 화면으로 간다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", "active", ["role-c"])]) });
    const view = mountApp(clients, "/", { routes: ROUTES });
    await waitFor(() => expect(view.router.state.location.pathname).toBe("/c"));
  });

  it("구성이 바뀌면(WS 재연결 뒤 다시 읽기) 토스트가 뜨고 사이드바가 갱신되며, 안내 화면을 보던 중 켜지면 원래 화면으로 바뀐다", async () => {
    const list = vi.fn(async () => [mod("m-1", "active", ["role-a"]), mod("m-2", "disabled", ["role-b"])]);
    const { clients, ws } = createFakeClients({ listModules: list });
    mountApp(clients, "/b", { routes: ROUTES });
    await screen.findByRole("heading", { name: "이 기능은 꺼져 있습니다" });
    list.mockImplementation(async () => [mod("m-1", "active", ["role-a"]), mod("m-2", "active", ["role-b"])]);
    await act(async () => {
      ws.setStatus("closed");
      ws.setStatus("open");
    });
    expect(await screen.findByText("서버의 기능 구성이 바뀌었습니다")).toBeTruthy();
    expect(await screen.findByText("기능이 켜졌습니다")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("heading", { name: "이 기능은 꺼져 있습니다" })).toBeNull());
    expect(within(nav()).getByRole("link", { name: "팀 구성" })).toBeTruthy();
  });

  it("저장 안 된 변경이 있는 화면은 꺼져도 내리지 않고 경고 배너만 얹는다", async () => {
    const list = vi.fn(async () => [mod("m-1", "active", ["role-a"])]);
    const { clients, ws } = createFakeClients({ listModules: list });
    const pages: PageTable = { "r-a": () => [{ index: true, element: <><UnsavedGuard dirty /><p>편집 중인 화면</p></> }] };
    mountApp(clients, "/a", { routes: ROUTES, pages });
    await screen.findByText("편집 중인 화면");
    list.mockImplementation(async () => [mod("m-1", "disabled", ["role-a"])]);
    await act(async () => {
      ws.setStatus("closed");
      ws.setStatus("open");
    });
    expect(await screen.findByText("서버에서 이 기능이 꺼졌습니다. 저장할 수 없을 수 있습니다.")).toBeTruthy();
    expect(screen.getByText("편집 중인 화면")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "이 기능은 꺼져 있습니다" })).toBeNull();
  });

  it("꺼진 화면의 g 키는 이동하지 않고 안내만 한다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", "active", ["role-a"])]) });
    const view = mountApp(clients, "/a", { routes: ROUTES });
    await waitFor(() => expect(within(nav()).getByRole("link", { name: "채팅" })).toBeTruthy());
    fireEvent.keyDown(document.body, { key: "g" });
    fireEvent.keyDown(document.body, { key: "x" });
    expect(await screen.findByText("‘에이전트’ 기능이 꺼져 있습니다")).toBeTruthy();
    expect(view.router.state.location.pathname).toBe("/a");
  });
});

describe("연동 부분", () => {
  const PARTS: LinkPartDef[] = [
    { id: "p-hide", requires: ["role-link"], onMissing: "hide" },
    { id: "p-disable", requires: ["role-link"], onMissing: "disable", noteKey: "sendUnavailable" },
  ];
  const pages: PageTable = {
    "r-a": () => [
      {
        index: true,
        element: (
          <div>
            <LinkPart id="p-hide"><span>숨길 부분</span></LinkPart>
            <LinkPart id="p-disable">
              {(s) => (
                <>
                  <input aria-label="입력" />
                  <button type="button" disabled={s.disabled}>전송</button>
                  {s.note ? <p>{s.note}</p> : null}
                </>
              )}
            </LinkPart>
          </div>
        ),
      },
    ],
  };

  it("hide는 자리를 남기지 않고, disable은 입력은 두되 동작만 막고 이유를 보인다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", "active", ["role-a"])]) });
    mountApp(clients, "/a", { routes: ROUTES, pages, linkParts: PARTS });
    expect(await screen.findByLabelText("입력")).toBeTruthy();
    expect(screen.queryByText("숨길 부분")).toBeNull();
    expect((screen.getByRole("button", { name: "전송" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/메시지를 보낼 수 없습니다/)).toBeTruthy();
  });

  it("역할을 가진 모듈이 켜져 있으면 둘 다 보이고, 꺼지면 해당 부분만 사라진다", async () => {
    const list = vi.fn(async () => [mod("m-1", "active", ["role-a"]), mod("link-1", "active", ["role-link"])]);
    const { clients, ws } = createFakeClients({ listModules: list });
    mountApp(clients, "/a", { routes: ROUTES, pages, linkParts: PARTS });
    expect(await screen.findByText("숨길 부분")).toBeTruthy();
    expect((screen.getByRole("button", { name: "전송" }) as HTMLButtonElement).disabled).toBe(false);
    list.mockImplementation(async () => [mod("m-1", "active", ["role-a"]), mod("link-1", "disabled", ["role-link"])]);
    await act(async () => {
      ws.setStatus("closed");
      ws.setStatus("open");
    });
    await waitFor(() => expect(screen.queryByText("숨길 부분")).toBeNull());
    expect(screen.getByLabelText("입력")).toBeTruthy();
  });
});
