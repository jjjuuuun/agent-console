import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, NETWORK_ERROR_CODE } from "@agent-console/api-client";
import type { WorkspaceSettings } from "@agent-console/contracts";
import type { I18nInfo, MessageCatalog } from "@agent-console/contracts/i18n";
import { AppRoot } from "../app/AppRoot";
import { BootError } from "../app/boot";
import { BOOT_RETRY } from "../app/bootRetry";
import { createAppQueryClient } from "../app/queries";
import { createSafeStorage } from "../app/storage";
import { SETTINGS_SECTIONS, SettingsScreen } from "../features/settings/SettingsScreen";
import { createFakeClients } from "../testing/fakes";
import { mountApp } from "../testing/screenHarness";
import { buildAppRoutes } from "../shell/routes";
import { LANGUAGE_STORAGE_KEY } from "./languageStorage";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "#");
  document.documentElement.lang = "";
});
const LONG = { timeout: 15_000 };
const pages = { settings: () => [{ index: true, element: <SettingsScreen sections={SETTINGS_SECTIONS} /> }] };

const info = (codes: string[]): I18nInfo => ({
  languages: codes.map((code) => ({ code, sources: code === "xx-test" ? ["user-folder"] : [], complete: code !== "xx-test", missing: code === "xx-test" ? 3 : 0 })),
  default_language: "en",
  fallback_language: "en",
});
/** 저장하는 메모리 저장소(`createSafeStorage(null)`은 아무것도 기억하지 않는다) */
function memoryStorage() {
  const map = new Map<string, string>();
  return createSafeStorage({
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() {
      return map.size;
    },
  } as Storage);
}
const notFound = () => new ApiError(404, { code: "not_found", message: "no" });

function mount(rest: Record<string, unknown> = {}, storage = memoryStorage()) {
  const fake = createFakeClients({ getI18nInfo: vi.fn(async () => info(["en", "ko", "xx-test"])), ...rest });
  const view = mountApp(fake.clients, "/settings#appearance", { pages, storage });
  return { ...view, ...fake, storage };
}
/** 값(언어 코드)으로 라디오를 찾는다(자동 행의 "지금: 한국어"와 이름이 겹치지 않게) */
const radio = (code: string) => document.querySelector<HTMLInputElement>(`input[type="radio"][value="${code}"]`)!;
const group = () => screen.findByRole("radiogroup", { name: "언어" }, LONG);

describe("설정 › 화면 › 언어", () => {
  it("선택지 = 자동 + 앱 묶음 + 서버 언어(코드순), 이름은 그 언어 자기 이름, 모르는 코드는 코드 그대로", async () => {
    mount();
    const list = await group();
    await waitFor(() => expect(within(list).getAllByRole("radio")).toHaveLength(4), LONG);
    const radios = within(list).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.value).slice(1)).toEqual(["en", "ko", "xx-test"]);
    expect(within(list).getByText("English").getAttribute("lang")).toBe("en");
    expect(within(list).getByText("한국어").getAttribute("lang")).toBe("ko");
    expect(within(list).getAllByText("xx-test").length).toBeGreaterThan(0); // 이름 = 코드(목록·코드 상수 없음)
    expect(within(list).getByText("일부만 번역됨")).toBeTruthy();
    expect(within(list).getByText(/출처: user-folder/)).toBeTruthy();
    expect(radios[0]!.checked).toBe(true); // 설정값 없음 = 자동
  });

  it("설정값이 없으면 자동이 선택돼 있고 '지금: 한국어'를 보인다", async () => {
    mount();
    const list = await group();
    const auto = within(list).getAllByRole("radio")[0] as HTMLInputElement;
    expect(auto.checked).toBe(true);
    expect(within(list).getByText("지금: 한국어")).toBeTruthy();
  });

  it("영어를 고르면 새로고침 없이 화면 문구가 바뀌고, 그 칸만 저장하며, html lang·알림·저장소가 맞다", async () => {
    const { fake, storage } = (() => {
      const f = createFakeClients({ getI18nInfo: vi.fn(async () => info(["en", "ko"])) });
      return { fake: f, storage: memoryStorage() };
    })();
    // 저장된 다른 설정은 그대로여야 한다
    const doc: WorkspaceSettings = { chat: { x: 1 } as never };
    fake.rest.getSettingsVersioned.mockImplementation(async () => ({ value: doc, version_hash: "h1" }));
    mountApp(fake.clients, "/settings#appearance", { pages, storage });
    const list = await group();
    await waitFor(() => expect(within(list).getAllByRole("radio")).toHaveLength(3), LONG);
    fireEvent.click(radio("en"));
    // 준비 전에는 이전 언어 그대로(섞이지 않는다)
    expect(screen.queryByRole("heading", { name: "Appearance" })).toBeNull();
    expect(await screen.findByRole("heading", { name: "Appearance", level: 2 }, LONG)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Settings", level: 1 })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Settings sections" })).toBeTruthy();
    expect(screen.getByRole("radiogroup", { name: "Language" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");
    expect(storage.get(LANGUAGE_STORAGE_KEY)).toBe("en");
    expect(screen.getByTestId("language-announcer").textContent).toBe("Language changed to English");
    await waitFor(() => expect(fake.rest.putSettingsVersioned).toHaveBeenCalledTimes(1), LONG);
    expect(fake.rest.putSettingsVersioned).toHaveBeenCalledWith({ chat: { x: 1 }, ui: { language: "en" } }, "h1");
    // 다시 한국어로(자동이 아니라 직접)
    fireEvent.click(radio("ko"));
    expect(await screen.findByRole("heading", { name: "화면", level: 2 }, LONG)).toBeTruthy();
    expect(document.documentElement.lang).toBe("ko");
  });

  it("저장된 ui.language가 있으면 첫 화면을 그 언어로 맞춘다(알림 없음)", async () => {
    const f = createFakeClients({ getI18nInfo: vi.fn(async () => info(["en", "ko"])) });
    f.rest.getSettingsVersioned.mockImplementation(async () => ({ value: { ui: { language: "en" } }, version_hash: "h1" }));
    mountApp(f.clients, "/settings#appearance", { pages, storage: createSafeStorage(null) });
    expect(await screen.findByRole("heading", { name: "Appearance", level: 2 }, LONG)).toBeTruthy();
    expect(screen.getByTestId("language-announcer").textContent).toBe("");
    expect(f.rest.putSettingsVersioned).not.toHaveBeenCalled();
  });

  it("저장이 실패해도 화면은 새 언어이고 경고 + [Try again]이 나오며, 다시 시도하면 저장된다", async () => {
    const f = createFakeClients({ getI18nInfo: vi.fn(async () => info(["en", "ko"])) });
    let fail = true;
    f.rest.putSettingsVersioned.mockImplementation(async (next: WorkspaceSettings) => {
      if (fail) throw new ApiError(500, { code: "internal_error", message: "boom" });
      return { value: next, version_hash: "h9" };
    });
    mountApp(f.clients, "/settings#appearance", { pages, storage: createSafeStorage(null) });
    const list = await group();
    await waitFor(() => expect(within(list).getAllByRole("radio")).toHaveLength(3), LONG);
    fireEvent.click(radio("en"));
    expect(await screen.findByText(/Language changed, but saving it to the server failed/, {}, LONG)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Appearance", level: 2 })).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByText(/saving it to the server failed/)).toBeNull(), LONG);
  });

  it("서버에 i18n 기능이 없으면(404) 앱 묶음 언어만 나오고 안내 한 줄, 바꾸기는 동작한다", async () => {
    const f = createFakeClients({
      getI18nInfo: vi.fn(async () => {
        throw notFound();
      }),
      getI18nCatalog: vi.fn(async () => null),
    });
    mountApp(f.clients, "/settings#appearance", { pages, storage: createSafeStorage(null) });
    const list = await group();
    await waitFor(() => expect(screen.queryByText("불러오는 중…")).toBeNull(), LONG);
    expect(within(list).getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByText(/서버가 주는 문구.*원문으로 보입니다/)).toBeTruthy();
    fireEvent.click(radio("en"));
    expect(await screen.findByRole("heading", { name: "Appearance", level: 2 }, LONG)).toBeTruthy();
  });

  it("서버 묶음이 앱 문구를 덮는다(웹 재빌드 없이 문구 수정)", async () => {
    const catalog: MessageCatalog = { language: "en", text: {}, codes: {}, ns: { settings: { sections: { appearance: "Look and feel" } } } };
    const f = createFakeClients({ getI18nInfo: vi.fn(async () => info(["en", "ko"])), getI18nCatalog: vi.fn(async (lang: string) => (lang === "en" ? catalog : null)) });
    mountApp(f.clients, "/settings#appearance", { pages, storage: createSafeStorage(null) });
    const list = await group();
    await waitFor(() => expect(within(list).getAllByRole("radio")).toHaveLength(3), LONG);
    fireEvent.click(radio("en"));
    expect(await screen.findByRole("heading", { name: "Look and feel", level: 2 }, LONG)).toBeTruthy();
  });

  it("서버 묶음을 못 받으면 앱 문구만 바뀌고 안내 한 줄", async () => {
    const f = createFakeClients({
      getI18nInfo: vi.fn(async () => info(["en", "ko"])),
      getI18nCatalog: vi.fn(async () => {
        throw new ApiError(500, { code: "internal_error", message: "x" });
      }),
    });
    mountApp(f.clients, "/settings#appearance", { pages, storage: createSafeStorage(null) });
    const list = await group();
    await waitFor(() => expect(within(list).getAllByRole("radio")).toHaveLength(3), LONG);
    fireEvent.click(radio("en"));
    expect(await screen.findByText(/Couldn't load the server text for this language/, {}, LONG)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Appearance", level: 2 })).toBeTruthy();
  });

  it("키보드: 화살표로 옮기며 고르고, 연타해도 마지막 선택만 반영된다", async () => {
    const { rest } = mount({ getI18nInfo: vi.fn(async () => info(["en", "ko"])) });
    const list = await group();
    await waitFor(() => expect(within(list).getAllByRole("radio")).toHaveLength(3), LONG);
    const en = radio("en");
    fireEvent.click(en);
    fireEvent.click(radio("ko"));
    fireEvent.click(en);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Appearance", level: 2 })).toBeTruthy(), LONG);
    await waitFor(() => expect(rest.putSettingsVersioned).toHaveBeenCalledTimes(1), LONG);
  });

  it("묶음에 없는 언어가 저장돼 있으면 선택된 비활성 행과 안내가 나온다", async () => {
    const f = createFakeClients({ getI18nInfo: vi.fn(async () => info(["en", "ko"])) });
    f.rest.getSettingsVersioned.mockImplementation(async () => ({ value: { ui: { language: "zz" } }, version_hash: "h" }));
    mountApp(f.clients, "/settings#appearance", { pages, storage: createSafeStorage(null) });
    expect(await screen.findByText("zz (사용할 수 없음)", {}, LONG)).toBeTruthy();
    expect(screen.getByText("저장된 언어를 쓸 수 없어 자동으로 보입니다.")).toBeTruthy();
  });
});

describe("서버에 닿기 전 첫 화면", () => {
  const failing = (storage = memoryStorage()) => {
    const createClients = vi.fn().mockRejectedValue(new BootError("http://127.0.0.1:8765", new ApiError(0, { code: NETWORK_ERROR_CODE, message: "Failed to fetch" }), false));
    const router = createMemoryRouter(buildAppRoutes(), { initialEntries: ["/settings"] });
    render(<AppRoot createClients={createClients} router={router} storage={storage} queryClient={createAppQueryClient({ retry: false })} bootRetry={{ ...BOOT_RETRY, giveUpMs: 0, notReadyGiveUpMs: 0 }} />);
  };
  it("저장된 언어가 en이면 연결 실패 화면이 영어로 나온다(브라우저가 ko여도)", async () => {
    const storage = memoryStorage();
    storage.set(LANGUAGE_STORAGE_KEY, "en");
    failing(storage);
    expect(await screen.findByText("Can't connect to the server", {}, LONG)).toBeTruthy();
    expect(screen.getByText(/Check that the server \(http:\/\/127\.0\.0\.1:8765\) is running/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");
  });
  it("저장값이 없으면 브라우저 언어(테스트 환경 ko)를 따른다", async () => {
    failing();
    expect(await screen.findByText("서버에 연결할 수 없습니다", {}, LONG)).toBeTruthy();
    await act(async () => {});
    expect(document.documentElement.lang).toBe("ko");
  });
});
