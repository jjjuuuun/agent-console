import { act, cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MessageCatalog } from "@agent-console/contracts/i18n";
import { createI18n } from "@agent-console/i18n";
import { AppI18nProvider } from "../i18n";
import { createSafeStorage } from "./storage";
import { LANGUAGE_HOLD_TEST_ID, LanguageProvider } from "./LanguageProvider";

// 서버·설정·모듈 연결은 가짜로 바꾼다(여기서는 첫 화면 언어 맞추기 때 본문을 보류하는지만 본다).
const calls = vi.hoisted(() => ({
  rest: {
    getI18nInfo: async (): Promise<unknown> => null,
    getI18nCatalog: async (): Promise<unknown> => null,
  },
  settings: { data: undefined as unknown, isPending: false },
}));
vi.mock("./ApiContext", () => ({ useApi: () => ({ rest: calls.rest }) }));
vi.mock("./queries", () => ({ queryKeys: { settings: () => ["settings"] }, useWorkspaceSettings: () => calls.settings }));
vi.mock("../modules", () => ({ useRequires: () => ({ phase: "unmet" }) }));

const storage = createSafeStorage({ getItem: () => null, setItem: () => undefined, removeItem: () => undefined, key: () => null, length: 0 } as unknown as Storage);

function mount(holdMs?: number) {
  const i18n = createI18n({ language: "ko", bundled: { ko: { app: { hi: "안녕" } }, en: { app: { hi: "Hello" } } } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AppI18nProvider i18n={i18n}>
        <LanguageProvider i18n={i18n} storage={storage} {...(holdMs === undefined ? {} : { holdMs })}>
          <p>본문</p>
        </LanguageProvider>
      </AppI18nProvider>
    </QueryClientProvider>,
  );
  return i18n;
}

beforeEach(() => {
  vi.useFakeTimers();
  calls.rest.getI18nInfo = async () => null;
  calls.rest.getI18nCatalog = async () => null;
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("LanguageProvider: 첫 언어 맞추기가 끝나기 전에는 본문을 보류한다", () => {
  it("서버 묶음이 도착하기 전에는 본문 대신 빈 자리(aria-busy), 도착하면 본문", async () => {
    let release: (value: MessageCatalog | null) => void = () => undefined;
    calls.rest.getI18nCatalog = () => new Promise((resolve) => (release = resolve));
    mount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByTestId(LANGUAGE_HOLD_TEST_ID).getAttribute("aria-busy")).toBe("true");
    expect(screen.queryByText("본문")).toBeNull();
    await act(async () => {
      release(null);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.queryByTestId(LANGUAGE_HOLD_TEST_ID)).toBeNull();
    expect(screen.getByText("본문")).toBeTruthy();
  });

  it("서버가 응답하지 않아도 holdMs가 지나면 본문을 그린다(오래 막지 않는다)", async () => {
    calls.rest.getI18nCatalog = () => new Promise(() => undefined);
    mount(1500);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.queryByText("본문")).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(screen.getByText("본문")).toBeTruthy();
  });

  it("holdMs가 0이면 기다리지 않고 바로 그린다", () => {
    mount(0);
    expect(screen.getByText("본문")).toBeTruthy();
  });
});
