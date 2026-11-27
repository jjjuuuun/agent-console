import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, type BackendDescriptor, type BackendReadiness } from "@agent-console/contracts";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { StorageProvider } from "../../app/StorageContext";
import { createSafeStorage } from "../../app/storage";
import { AppI18nProvider } from "../../i18n/AppI18n";
import { createFakeClients } from "../../testing/fakes";
import { createTestAppI18n } from "../../testing/TestI18n";
import { BackendReadinessSection } from "../backendReadiness";

afterEach(cleanup);

const NOW = Date.now() / 1000;
const backend = { id: "be-q", title: "백엔드 큐", capabilities: { status: true, probe: false, login: true }, login_methods: [{ id: "mt-1", label: "방법 하나", needs_browser: true }] } as BackendDescriptor;
const loggedOut: BackendReadiness = { backend_id: "be-q", state: "zz", tone: "warn", summary: "로그인 안 됨", checked_at: NOW, actions: [{ kind: "login", label: "구독으로 로그인", primary: true }] };

describe("로그인 오류 문구는 화면 언어를 따른다", () => {
  it("시작이 알려진 오류 코드로 실패해 떠 있는 채로 언어를 바꾸면 새 언어 문구로 바뀐다", async () => {
    const { clients } = createFakeClients({
      listBackendStatuses: vi.fn(async () => [loggedOut]),
      startBackendLogin: vi.fn(async () => {
        throw new ApiError(409, { code: ERROR_CODES.PROJECT_CONFIG_READONLY, message: "server original" });
      }),
    });
    const storage = createSafeStorage(null);
    const router = createMemoryRouter([{ path: "*", element: <BackendReadinessSection backends={[backend]} /> }], { initialEntries: ["/x"] });
    const i18n = createTestAppI18n("ko");
    render(
      <AppI18nProvider i18n={i18n}>
        <QueryClientProvider client={createAppQueryClient({ retry: false })}>
          <ApiProvider clients={clients}>
            <StorageProvider storage={storage}>
              <RouterProvider router={router} />
            </StorageProvider>
          </ApiProvider>
        </QueryClientProvider>
      </AppI18nProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "구독으로 로그인" }));
    fireEvent.click(await screen.findByRole("button", { name: "로그인 시작" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(".ac-banner")?.textContent ?? "").not.toBe(""));
    const ko = dialog.querySelector(".ac-banner")?.textContent ?? "";
    expect(ko).not.toBe("server original");
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    const en = screen.getByRole("dialog").querySelector(".ac-banner")?.textContent ?? "";
    expect(en).toContain("read-only");
    expect(en).not.toBe(ko);
  });
});
