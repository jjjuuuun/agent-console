import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { WorkspaceSettings } from "@agent-console/contracts";
import { ApiError, NETWORK_ERROR_CODE } from "@agent-console/api-client";
import { createFakeClients, pendingInteraction, versionConflict } from "../testing/fakes";
import type { ApiClients } from "./apiClients";
import { AppRoot } from "./AppRoot";
import { BootError } from "./boot";
import { createAppQueryClient } from "./queries";
import { createSafeStorage } from "./storage";
import { buildAppRoutes, preloadScreens } from "../shell/routes";

beforeAll(preloadScreens, 120_000);

afterEach(cleanup);

function mount(clients: ApiClients, path: string) {
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  const view = render(
    <AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />,
  );
  return { router, ...view };
}

describe("부팅", () => {
  it("연결 실패: 시도한 주소를 안내하고(토큰 없음) 다시 시도하면 화면이 열린다", async () => {
    const { clients } = createFakeClients();
    const createClients = vi
      .fn()
      .mockRejectedValueOnce(new BootError("http://127.0.0.1:8765", new ApiError(0, { code: NETWORK_ERROR_CODE, message: "Failed to fetch" }), true))
      .mockResolvedValue(clients);
    const router = createMemoryRouter(buildAppRoutes(), { initialEntries: ["/settings"] });
    render(<AppRoot createClients={createClients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
    expect(await screen.findByText("서버에 연결할 수 없습니다")).toBeTruthy();
    expect(screen.getAllByText(/http:\/\/127\.0\.0\.1:8765/).length).toBeGreaterThan(0);
    expect(screen.getByText(/허용 출처/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByRole("heading", { name: "설정", level: 1 })).toBeTruthy();
    expect(createClients).toHaveBeenCalledTimes(2);
  });

  it("인증이 거부되면 전역 배너와 새로고침 버튼을 보여 준다", async () => {
    const { clients } = createFakeClients();
    const onReload = vi.fn();
    const router = createMemoryRouter(buildAppRoutes(), { initialEntries: ["/chat"] });
    render(
      <AppRoot
        createClients={async (hooks) => {
          setTimeout(hooks.onAuthRejected, 0);
          return clients;
        }}
        router={router}
        storage={createSafeStorage(null)}
        onReload={onReload}
        queryClient={createAppQueryClient({ retry: false })}
      />,
    );
    expect(await screen.findByText("인증이 만료되었습니다.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
    expect(onReload).toHaveBeenCalled();
  });

  it("서버와 웹의 계약 버전이 다르면 경고 배너", async () => {
    const { clients } = createFakeClients();
    clients.meta.contractsVersion = "0.0.0-other";
    mount(clients, "/chat");
    expect(await screen.findByText(/버전이 다릅니다/)).toBeTruthy();
  });
});

describe("앱 셸", () => {
  it("사이드바 항목은 라우트 설정 데이터에서 묶음별로 생성되고 현재 화면이 aria-current다", async () => {
    mount(createFakeClients().clients, "/agents");
    const nav = await screen.findByRole("navigation", { name: "주 메뉴" });
    // 서버 모듈 목록을 받은 뒤에 항목이 채워진다(받기 전에는 스켈레톤)
    await waitFor(() => expect(within(nav).getAllByRole("link")).toHaveLength(8));
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.querySelector(".ac-sidebar-label")?.textContent)).toEqual(["팀 구성", "에이전트", "리소스", "채팅", "실행 기록", "사용량", "로그", "설정"]);
    // 묶음 제목은 라우트의 group + 묶음 데이터에서 온다
    expect(within(nav).getByRole("list", { name: "구성" })).toBeTruthy();
    expect(within(nav).getByRole("list", { name: "실행" })).toBeTruthy();
    expect(within(nav).getByRole("list", { name: "관측" })).toBeTruthy();
    expect(within(nav).getByRole("link", { name: "에이전트" }).getAttribute("aria-current")).toBe("page");
    // 설정은 position:footer 데이터 → 주 메뉴 아래 고정 줄의 글자 있는 항목(도구줄이 아니다)
    expect(within(nav).getByRole("link", { name: "설정" }).getAttribute("href")).toBe("/settings");
    expect(nav.querySelector('[data-position="footer"] [data-id="settings"]')).not.toBeNull();
    expect(within(screen.getByRole("group", { name: "도구" })).queryByRole("link", { name: "설정" })).toBeNull();
    await waitFor(() => expect(document.title).toBe("에이전트 · Agent Console"));
  });

  it("도구줄은 도움말 · 테마 · 접기 3개, 접기 버튼은 이름이 하나이고 aria-expanded로 상태를 알린다", async () => {
    mount(createFakeClients().clients, "/chat");
    const tools = await screen.findByRole("group", { name: "도구" });
    const names = within(tools).getAllByRole("button").map((e) => e.getAttribute("aria-label"));
    expect(names[0]).toMatch(/^단축키 도움말/);
    expect(names[1]).toMatch(/^테마: /);
    expect(names[2]).toBe("사이드바 접기/펴기");
    expect(names).toHaveLength(3);
    const toggle = within(tools).getByRole("button", { name: "사이드바 접기/펴기" });
    expect(toggle.tabIndex).toBe(0);
    const before = toggle.getAttribute("aria-expanded");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe(before === "true" ? "false" : "true");
    expect(toggle.getAttribute("aria-label")).toBe("사이드바 접기/펴기");
    expect(toggle.getAttribute("title")).toBeNull(); // 느린 기본 title 대신 150ms 툴팁
    expect(toggle.closest(".ac-tip-host")!.querySelector(".ac-tip")!.textContent).toMatch(/^사이드바 \(.+\)$/);
  });

  it("연결이 정상이면 사이드바에 연결 표시가 없고 띠도 없다", async () => {
    mount(createFakeClients().clients, "/chat");
    const side = await screen.findByRole("complementary", { name: "사이드바" });
    expect(within(side).queryByRole("button", { name: /설치/ })).toBeNull();
    expect(side.querySelector(".app-conn")).toBeNull();
    expect(document.querySelector(".app-conn-banner")).toBeNull();
  });

  it("모듈을 끄면 그 항목과 비어 버린 묶음 제목이 사라진다", async () => {
    const mod = (id: string, roles: string[]) => ({ id, kind: "k", version: "0.0.1", status: "active", web_roles: roles });
    // 정의(구성) 역할과 사용량·로그를 끄고, 대화·실행 기록만 켠다
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-1", ["conversations", "runs"])]) });
    mount(clients, "/chat");
    const nav = await screen.findByRole("navigation", { name: "주 메뉴" });
    await waitFor(() => expect(within(nav).getAllByRole("link").map((l) => l.querySelector(".ac-sidebar-label")?.textContent)).toEqual(["채팅", "실행 기록", "설정"]));
    expect(within(nav).getByRole("list", { name: "실행" })).toBeTruthy();
    expect(within(nav).queryByText("구성")).toBeNull();
    expect(within(nav).queryByText("관측")).toBeNull();
  });

  it("루트: 팀 구성이 0개면 구성 역할 화면, 1개 이상이면 첫 화면(5.2R.25)", async () => {
    const empty = mount(createFakeClients().clients, "/");
    await waitFor(() => expect(empty.router.state.location.pathname).toBe("/teams"));
    empty.unmount();
    const some = mount(createFakeClients({ listGraphs: vi.fn(async () => [{ id: "g-1", name: "팀 하나", version_hash: "h", node_count: 0, edge_count: 0 }]) }).clients, "/");
    await waitFor(() => expect(some.router.state.location.pathname).toBe("/chat"));
    some.unmount();
  });

  it("루트는 첫 화면으로, 이전 경로는 새 경로로 옮기고, 없는 경로(/console 포함)는 안내한다", async () => {
    const { router, unmount } = mount(createFakeClients({ listGraphs: vi.fn(async () => [{ id: "g-1", name: "팀 하나", version_hash: "h", node_count: 0, edge_count: 0 }]) }).clients, "/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/chat"));
    await router.navigate("/graphs/g1?x=1");
    await waitFor(() => expect(router.state.location.pathname + router.state.location.search).toBe("/teams/g1?x=1"));
    await router.navigate("/console");
    expect(await screen.findByText("찾을 수 없는 화면입니다")).toBeTruthy();
    unmount();
  });

  it("페이지 표에 없는 화면은 자리표시로 열린다(라우트 설정 데이터만으로 제목·아이콘)", async () => {
    const router = createMemoryRouter(buildAppRoutes({ pages: {}, platform: "other" }), { initialEntries: ["/teams/abc"] });
    render(<AppRoot createClients={async () => createFakeClients().clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
    const frame = await screen.findByRole("heading", { name: "팀 구성", level: 1 });
    expect(frame.closest("[data-placeholder]")).toBeTruthy();
  });

  it("응답 대기 상호작용: 사이드바 배지와 문서 제목, Alt+J로 가장 오래 기다린 대화로 이동", async () => {
    const { clients, ws } = createFakeClients();
    const { router } = mount(clients, "/settings");
    const side = await screen.findByRole("navigation", { name: "주 메뉴" });
    // 상호작용 구독은 서버 모듈 목록을 받은 뒤에 시작한다
    await waitFor(() => expect(within(side).getAllByRole("link").length).toBeGreaterThan(1));
    act(() => {
      ws.emitInteraction(pendingInteraction("i2", "conv-late", 20));
      ws.emitInteraction(pendingInteraction("i1", "conv-early", 10));
    });
    expect(await screen.findByLabelText("응답 대기 2건")).toBeTruthy();
    await waitFor(() => expect(document.title).toBe("(2) 설정 · Agent Console"));
    fireEvent.keyDown(document.body, { key: "j", altKey: true });
    await waitFor(() => expect(router.state.location.pathname).toBe("/chat/conv-early"));
    act(() => ws.emitInteraction({ ...pendingInteraction("i1", "conv-early", 10), status: "answered" as never }));
    await waitFor(() => expect(screen.getByLabelText("응답 대기 1건")).toBeTruthy());
  });

  it("`g` 다음 글자로 이동하고, 설정 ui.keybindings가 기본 키를 덮어쓴다", async () => {
    const settings: WorkspaceSettings = { ui: { keybindings: { "goto.teams": "g x" } } };
    const { clients } = createFakeClients({ getSettingsVersioned: vi.fn(async () => ({ value: settings, version_hash: "s1" })) });
    const { router } = mount(clients, "/chat");
    await screen.findByRole("navigation", { name: "주 메뉴" });
    fireEvent.keyDown(document.body, { key: "g" });
    fireEvent.keyDown(document.body, { key: "a" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/agents"));
    await waitFor(() => {
      fireEvent.keyDown(document.body, { key: "g" });
      fireEvent.keyDown(document.body, { key: "x" });
      expect(router.state.location.pathname).toBe("/teams");
    });
  });

  it("Ctrl+K 빠른 이동: 화면 그룹과 목록 그룹, 한 그룹이 실패해도 나머지는 나온다", async () => {
    const { clients } = createFakeClients({
      listAgents: vi.fn(async () => { throw new Error("실패"); }),
      listGraphs: vi.fn(async () => [{ id: "g-1", name: "팀 하나", version_hash: "h", node_count: 0, edge_count: 0 }]),
    });
    const { router } = mount(clients, "/chat");
    await screen.findByRole("navigation", { name: "주 메뉴" });
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: "빠른 이동" });
    expect(await within(dialog).findByText("팀 하나")).toBeTruthy();
    expect(within(dialog).getByText("화면")).toBeTruthy();
    expect(within(dialog).queryByText("에이전트", { selector: ".ac-palette-group-title" })).toBeNull();
    fireEvent.click(within(dialog).getByText("팀 하나"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/teams/g-1"));
  });

  it("?로 도움말을 열면 실제 적용 중인 키 표를 보인다", async () => {
    mount(createFakeClients().clients, "/chat");
    await screen.findByRole("navigation", { name: "주 메뉴" });
    fireEvent.keyDown(document.body, { key: "?" });
    const dialog = await screen.findByRole("dialog", { name: "단축키" });
    expect(within(dialog).getByText("빠른 이동 열기")).toBeTruthy();
    expect(within(dialog).getByText("채팅(으)로 이동")).toBeTruthy();
  });
});

describe("도움말 시작 순서", () => {
  it("도움말 맨 위 [시작 순서 다시 보기]가 시작하기 대화상자를 연다", async () => {
    mount(createFakeClients().clients, "/runs");
    await screen.findByRole("navigation", { name: "주 메뉴" });
    fireEvent.keyDown(document.body, { key: "?" });
    const help = await screen.findByRole("dialog", { name: "단축키" });
    fireEvent.click(within(help).getByRole("button", { name: "시작 순서 다시 보기" }));
    const dialog = await screen.findByRole("dialog", { name: "시작하기" });
    expect(await within(dialog).findByText("팀 만들기")).toBeTruthy();
  });
});

describe("설정 화면", () => {
  it("빈 workspace: 안내와 기본값 배지, 값을 바꾸면 저장 안 됨 → 저장은 If-Match로 보낸다", async () => {
    const { clients, rest } = createFakeClients();
    mount(clients, "/settings#chat");
    const chat = await screen.findByRole("region", { name: "채팅" });
    const radios = await within(chat).findAllByRole("radio");
    expect(radios.length).toBeGreaterThan(0);
    expect(within(chat).getAllByText(/^기본값:/).length).toBeGreaterThan(0);
    // 실행 중 새 메시지: queue(기본) → reject
    const reject = within(chat).getByRole("radio", { name: /거절/ });
    expect(screen.getAllByText("저장됨").length).toBeGreaterThan(0);
    // 상속 상태에서도 바로 편집된다(건드리면 이 층에서 지정)
    fireEvent.click(reject);
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.putSettingsVersioned).toHaveBeenCalled());
    const [sent, hash] = rest.putSettingsVersioned.mock.calls[0] as [WorkspaceSettings, string];
    expect(hash).toBe("s1");
    // 바꾼 키만 들어간다: 폼이 채운 다른 기본값이 파일로 새지 않는다.
    expect(sent).toEqual({ chat: { busy_policy: "reject" } });
    await waitFor(() => expect(screen.getByText("저장됨")).toBeTruthy());
  });

  it("GET 원문 -> 한 키만 바꿔 PUT: 명시한 값은 유지되고 건드리지 않은 기본값은 늘어나지 않는다", async () => {
    // 기본값과 같은 값을 일부러 지정한 키(busy_policy: queue)와 다른 섹션 값이 이미 저장돼 있다.
    const stored: WorkspaceSettings = { chat: { busy_policy: "queue" }, ui: { keybindings: { "goto.teams": "g x" } } };
    const { clients, rest } = createFakeClients({ getSettingsVersioned: vi.fn(async () => ({ value: stored, version_hash: "s1" })) });
    mount(clients, "/settings#delegation");
    const delegation = await screen.findByRole("region", { name: "위임" });
    const depthRow = (await within(delegation).findByRole("spinbutton", { name: /최대 위임 깊이/ })).closest(".ac-sf-prov-row") as HTMLElement;
    fireEvent.click(within(depthRow).getByRole("checkbox", { name: "정하지 않음" }));
    fireEvent.change(within(depthRow).getByRole("spinbutton"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest.putSettingsVersioned).toHaveBeenCalled());
    const [sent] = rest.putSettingsVersioned.mock.calls[0] as [WorkspaceSettings];
    expect(sent.chat).toEqual({ busy_policy: "queue" });
    expect(sent.ui).toEqual({ keybindings: { "goto.teams": "g x" } });
    expect(Object.keys(sent).sort()).toEqual(["chat", "delegation", "ui"]);
    expect(Object.keys(sent.delegation as object)).toEqual(["max_depth"]);
  });

  it("저장 충돌(412): 배너가 뜨고 저장은 비활성, 덮어쓰기는 서버 최신 해시로 다시 저장한다", async () => {
    let first = true;
    const { clients, rest } = createFakeClients({
      putSettingsVersioned: vi.fn(async (v: WorkspaceSettings) => {
        if (first) {
          first = false;
          throw versionConflict();
        }
        return { value: v, version_hash: "s9" };
      }),
      getSettingsVersioned: vi.fn(async () => ({ value: {}, version_hash: "s7" })),
    });
    mount(clients, "/settings#delegation");
    const delegation = await screen.findByRole("region", { name: "위임" });
    const depthRow = (await within(delegation).findByRole("spinbutton", { name: /최대 위임 깊이/ })).closest(".ac-sf-prov-row") as HTMLElement;
    fireEvent.click(within(depthRow).getByRole("checkbox", { name: "정하지 않음" }));
    fireEvent.change(within(depthRow).getByRole("spinbutton"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    const banner = await screen.findByRole("alert", { name: "저장 충돌" });
    expect(screen.getByRole("button", { name: "저장" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(within(banner).getByRole("button", { name: "내 변경으로 덮어쓰기" }));
    const confirm = await screen.findByRole("dialog", { name: "서버 버전을 덮어씁니다" });
    fireEvent.click(within(confirm).getByRole("button", { name: "내 변경으로 덮어쓰기" }));
    await waitFor(() => expect(rest.putSettingsVersioned).toHaveBeenCalledTimes(2));
    expect(rest.putSettingsVersioned.mock.calls[1]?.[1]).toBe("s7");
  });

  it("사용량 출처: 비공식 출처를 켜기 전에 확인하고, 그 설정이 초안에 들어간다", async () => {
    const { clients } = createFakeClients();
    mount(clients, "/settings#usage");
    const box = await screen.findByRole("checkbox", { name: "출처 둘 사용" });
    fireEvent.click(box);
    const dialog = await screen.findByRole("dialog", { name: "공식 문서가 없는 방식입니다" });
    expect(within(dialog).getByText("비공식 방식")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "켜기" }));
    await waitFor(() => expect((screen.getByRole("checkbox", { name: "출처 둘 사용" }) as HTMLInputElement).checked).toBe(true));
    expect(await screen.findByText("저장 안 됨")).toBeTruthy();
  });

  it("서버 정보는 읽기 전용이며 토큰을 보이지 않는다", async () => {
    mount(createFakeClients().clients, "/settings#server");
    const table = await screen.findByRole("table", { name: "서버 정보" });
    expect(within(table).getByText("http://fake.test")).toBeTruthy();
    expect(within(table).getByText("http://localhost:5173")).toBeTruthy();
    expect(document.body.textContent).not.toContain('"t"');
  });
});
