import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, type BackendDescriptor, type BackendLoginSession, type BackendReadiness } from "@agent-console/contracts";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { StorageProvider } from "../../app/StorageContext";
import { createSafeStorage } from "../../app/storage";
import { createFakeClients } from "../../testing/fakes";
import { BackendReadinessSection } from "../backendReadiness";
import { formatRemaining, isOpenableUrl } from "./types";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// 백엔드 id·문구는 전부 임의 값이다.
const NOW = Date.now() / 1000;
const backend = {
  id: "be-q",
  title: "백엔드 큐",
  capabilities: { status: true, probe: false, login: true, logout: true },
  login_methods: [{ id: "mt-1", label: "방법 하나로 로그인", notice: "본인 구독 안내 문구", writes: ["/home/x/.cred"], needs_browser: true }],
} as BackendDescriptor;
const base = { session_id: "s1", backend_id: "be-q", method_id: "mt-1", message: "서버 단계 안내", started_at: NOW, expires_at: NOW + 120 };
const waiting: BackendLoginSession = { ...base, phase: "waiting_user", open_url: "https://example.test/auth", needs_code: true, code_label: "코드 칸", accepts_keys: ["enter"], screen: ["화면 줄"] };
const loggedOut: BackendReadiness = { backend_id: "be-q", state: "zz", tone: "warn", summary: "로그인 안 됨", checked_at: NOW, actions: [{ kind: "login", label: "구독으로 로그인", primary: true }, { kind: "zz-unknown", label: "모르는 동작" }] };
const loggedIn: BackendReadiness = { backend_id: "be-q", state: "zz2", tone: "ok", summary: "로그인됨 상태", checked_at: NOW, actions: [{ kind: "logout", label: "로그아웃(연결 해제)" }] };

function setup(overrides: Record<string, unknown> = {}) {
  const { clients, rest } = createFakeClients({ listBackendStatuses: vi.fn(async () => [loggedOut]), getBackendStatus: vi.fn(async () => loggedIn), ...overrides });
  const mem = new Map<string, string>();
  const storage = createSafeStorage({ getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v), removeItem: (k: string) => void mem.delete(k), key: (i: number) => [...mem.keys()][i] ?? null, get length() { return mem.size; }, clear: () => mem.clear() } as Storage);
  const router = createMemoryRouter([{ path: "*", element: <BackendReadinessSection backends={[backend]} /> }], { initialEntries: ["/x"] });
  const queryClient = createAppQueryClient({ retry: false });
  render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider clients={clients}>
        <StorageProvider storage={storage}>
          <RouterProvider router={router} />
        </StorageProvider>
      </ApiProvider>
    </QueryClientProvider>,
  );
  return { rest, queryClient };
}

describe("types", () => {
  it("남은 시간·열 수 있는 주소", () => {
    expect(formatRemaining(1000 + 271, 1000 * 1000)).toBe("4:31");
    expect(formatRemaining(10, 99_000)).toBe("0:00");
    expect(isOpenableUrl("https://a.test")).toBe(true);
    expect(isOpenableUrl("javascript:alert(1)")).toBe(false);
    expect(isOpenableUrl(null)).toBe(false);
  });
});

describe("로그인 버튼", () => {
  it("서버가 준 primary login만 버튼이 되고 모르는 kind는 그리지 않는다", async () => {
    setup();
    expect(await screen.findByRole("button", { name: "구독으로 로그인" })).toBeTruthy();
    expect(screen.queryByText("모르는 동작")).toBeNull();
  });

  it("로그인된 상태는 non-primary logout을 … 메뉴에 둔다", async () => {
    setup({ listBackendStatuses: vi.fn(async () => [loggedIn]) });
    fireEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    expect(await screen.findByRole("menuitem", { name: "로그아웃(연결 해제)" })).toBeTruthy();
  });
});

describe("로그인 흐름", () => {
  it("확인 창(notice·writes) → 시작 → 코드 보내기(입력칸 비움) → 성공 시 상태 다시 읽기", async () => {
    let phase: BackendLoginSession["phase"] = "waiting_user";
    const start = vi.fn(async () => waiting);
    const get = vi.fn(async () => ({ ...waiting, phase, ...(phase === "succeeded" ? { message: "성공 문구", needs_code: false } : {}) }) as BackendLoginSession);
    const send = vi.fn(async () => undefined);
    const { rest, queryClient } = setup({ startBackendLogin: start, getBackendLogin: get, sendBackendLoginInput: send });
    fireEvent.click(await screen.findByRole("button", { name: "구독으로 로그인" }));
    const dialog = await screen.findByRole("dialog", { name: "방법 하나로 로그인" });
    expect(dialog.textContent).toContain("본인 구독 안내 문구");
    expect(dialog.textContent).toContain("/home/x/.cred");
    expect(document.activeElement?.textContent).toBe("로그인 시작");
    fireEvent.click(screen.getByRole("button", { name: "로그인 시작" }));
    await waitFor(() => expect(start).toHaveBeenCalledWith("be-q", {}));
    const link = (await screen.findByRole("link", { name: "로그인 페이지 열기" })) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("https://example.test/auth");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    const input = (await screen.findByLabelText("코드 칸")) as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(input.autocomplete).toBe("off");
    fireEvent.change(input, { target: { value: "SECRET-CODE-1" } });
    phase = "succeeded";
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(send).toHaveBeenCalledWith("s1", { text: "SECRET-CODE-1" }));
    expect(input.value).toBe("");
    // 쿼리 캐시·DOM 어디에도 코드가 없다
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain("SECRET-CODE-1");
    expect(document.body.innerHTML).not.toContain("SECRET-CODE-1");
    await waitFor(() => expect(screen.getByText("성공 문구")).toBeTruthy());
    await waitFor(() => expect(rest.getBackendStatus).toHaveBeenCalledWith("be-q"));
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByText("로그인됨 상태")).toBeTruthy();
  });

  it("취소는 DELETE를 부르고 취소 문구를 보인다, https 아닌 주소는 링크가 없다", async () => {
    const cancel = vi.fn(async () => ({ ...waiting, phase: "cancelled", message: "", open_url: null }) as BackendLoginSession);
    setup({ startBackendLogin: vi.fn(async () => ({ ...waiting, open_url: "http://plain.test/x" })), getBackendLogin: vi.fn(async () => ({ ...waiting, open_url: "http://plain.test/x" })), cancelBackendLogin: cancel });
    fireEvent.click(await screen.findByRole("button", { name: "구독으로 로그인" }));
    fireEvent.click(await screen.findByRole("button", { name: "로그인 시작" }));
    await screen.findByRole("button", { name: "취소" });
    expect(screen.queryByRole("link", { name: "로그인 페이지 열기" })).toBeNull();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("s1"));
    expect(await screen.findByText(/취소했습니다/)).toBeTruthy();
  });

  it("실패는 서버 문장·사유를 보이고 [다시 시도]로 다시 시작한다", async () => {
    const failed = { ...waiting, phase: "failed", reason: "zz_reason", message: "서버가 준 실패 문장", needs_code: false, open_url: null } as BackendLoginSession;
    const start = vi.fn(async () => failed);
    setup({ startBackendLogin: start, getBackendLogin: vi.fn(async () => failed) });
    fireEvent.click(await screen.findByRole("button", { name: "구독으로 로그인" }));
    fireEvent.click(await screen.findByRole("button", { name: "로그인 시작" }));
    expect(await screen.findByText("서버가 준 실패 문장")).toBeTruthy();
    expect(screen.getByText(/zz_reason/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(start).toHaveBeenCalledTimes(2));
  });

  it("login_busy는 이어 보기/그 로그인 취소를 준다", async () => {
    const busy = new ApiError(409, { code: ERROR_CODES.BACKEND_LOGIN_BUSY, message: "busy", details: { session_id: "other" } });
    const start = vi.fn(async () => {
      throw busy;
    });
    const get = vi.fn(async (sid: string) => ({ ...waiting, session_id: sid }));
    const cancel = vi.fn(async () => ({ ...waiting, phase: "cancelled" }) as BackendLoginSession);
    setup({ startBackendLogin: start, getBackendLogin: get, cancelBackendLogin: cancel });
    fireEvent.click(await screen.findByRole("button", { name: "구독으로 로그인" }));
    fireEvent.click(await screen.findByRole("button", { name: "로그인 시작" }));
    fireEvent.click(await screen.findByRole("button", { name: "여기서 이어 보기" }));
    await waitFor(() => expect(get).toHaveBeenCalledWith("other"));
    expect(await screen.findByRole("link", { name: "로그인 페이지 열기" })).toBeTruthy();
  });

  it("진행 중 세션이 있으면 열 때 이어 붙는다", async () => {
    const { rest } = setup({ getCurrentBackendLogin: vi.fn(async () => waiting), getBackendLogin: vi.fn(async () => waiting) });
    expect(await screen.findByRole("link", { name: "로그인 페이지 열기" })).toBeTruthy();
    expect(rest.getCurrentBackendLogin).toHaveBeenCalled();
  });

  it("폴링은 1초 간격이고 언마운트(대화상자 닫힘) 뒤에는 멈춘다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const get = vi.fn(async () => waiting);
    setup({ startBackendLogin: vi.fn(async () => waiting), getBackendLogin: get });
    fireEvent.click(await screen.findByRole("button", { name: "구독으로 로그인" }));
    fireEvent.click(await screen.findByRole("button", { name: "로그인 시작" }));
    await screen.findByRole("button", { name: "취소" });
    const before = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(get.mock.calls.length).toBeGreaterThanOrEqual(before + 2);
    cleanup();
    const after = get.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(get.mock.calls.length).toBe(after);
  });
});

describe("로그아웃", () => {
  it("확인 창이 터미널도 로그아웃된다고 알리고, 결과 뒤 상태를 다시 읽는다", async () => {
    const logout = vi.fn(async () => ({ backend_id: "be-q", ok: true, message: "서버 로그아웃 결과", finished_at: NOW }));
    const { rest } = setup({ listBackendStatuses: vi.fn(async () => [loggedIn]), logoutBackend: logout });
    fireEvent.click(await screen.findByRole("button", { name: "더 보기" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "로그아웃(연결 해제)" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("터미널");
    fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));
    await waitFor(() => expect(logout).toHaveBeenCalledWith("be-q"));
    expect(await screen.findByText("서버 로그아웃 결과")).toBeTruthy();
    await waitFor(() => expect(rest.getBackendStatus).toHaveBeenCalledWith("be-q"));
  });
});
