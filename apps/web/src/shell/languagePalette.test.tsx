import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkspaceSettings } from "@agent-console/contracts";
import type { I18nInfo } from "@agent-console/contracts/i18n";
import { SETTINGS_SECTIONS, SettingsScreen } from "../features/settings/SettingsScreen";
import { createSafeStorage } from "../app/storage";
import { createFakeClients } from "../testing/fakes";
import { mountApp } from "../testing/screenHarness";

// 빠른 이동(Ctrl+K)의 "언어 바꾸기…" 명령(screen-i18n §2.4)과 문서 제목 갱신(§3-6).
afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "#");
  document.documentElement.lang = "";
});
const LONG = { timeout: 15_000 };
const pages = { settings: () => [{ index: true, element: <SettingsScreen sections={SETTINGS_SECTIONS} /> }] };
const info: I18nInfo = { languages: [{ code: "en", sources: [], complete: true, missing: 0 }, { code: "ko", sources: [], complete: true, missing: 0 }], default_language: "en", fallback_language: "en" };

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

describe("빠른 이동 › 언어 바꾸기…", () => {
  it("명령을 고르면 팔레트가 언어 목록으로 바뀌고, 고르면 화면 문구와 문서 제목이 바뀐다", async () => {
    const fake = createFakeClients({ getI18nInfo: vi.fn(async () => info) });
    const doc: WorkspaceSettings = {};
    fake.rest.getSettingsVersioned.mockImplementation(async () => ({ value: doc, version_hash: "h1" }));
    mountApp(fake.clients, "/settings", { pages, storage: memoryStorage() });
    await screen.findByRole("navigation", { name: "주 메뉴" }, LONG);
    await waitFor(() => expect(document.title).toBe("설정 · Agent Console"), LONG);
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: "빠른 이동" }, LONG);
    fireEvent.click(await within(dialog).findByText("언어 바꾸기…", {}, LONG));
    const languages = await screen.findByRole("dialog", { name: "언어 바꾸기" }, LONG);
    await waitFor(() => expect(within(languages).getByText("English")).toBeTruthy(), LONG);
    expect(within(languages).getByText("한국어")).toBeTruthy();
    expect(within(languages).getByText("현재")).toBeTruthy();
    fireEvent.click(within(languages).getByText("English"));
    await waitFor(() => expect(document.title).toBe("Settings · Agent Console"), LONG);
    expect(screen.getByRole("navigation", { name: "Main menu" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("en");
  });

  it("다시 열면 언어 목록이 아니라 평소 빠른 이동이다", async () => {
    mountApp(createFakeClients({ getI18nInfo: vi.fn(async () => info) }).clients, "/settings", { pages, storage: memoryStorage() });
    await screen.findByRole("navigation", { name: "주 메뉴" }, LONG);
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: "빠른 이동" }, LONG);
    fireEvent.click(await within(dialog).findByText("언어 바꾸기…", {}, LONG));
    await screen.findByRole("dialog", { name: "언어 바꾸기" }, LONG);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "언어 바꾸기" })).toBeNull(), LONG);
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    expect(await screen.findByRole("dialog", { name: "빠른 이동" }, LONG)).toBeTruthy();
  });
});
