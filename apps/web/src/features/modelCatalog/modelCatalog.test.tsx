import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyServerCatalog } from "@agent-console/i18n";
import type { ModelInfo } from "@agent-console/contracts";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";
import type { BackendModelCatalogResult } from "@agent-console/api-client";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { AppI18nProvider } from "../../i18n/AppI18n";
import { createFakeClients } from "../../testing/fakes";
import { createTestAppI18n } from "../../testing/TestI18n";
import { BackendConnectContext } from "../backendConnect";
import { ModelWidget, type ModelOptions } from "../library";
import { ModelCatalogStatus } from "./ModelCatalogStatus";

afterEach(cleanup);
const LONG = { timeout: 15_000 };
const NOW = Date.now() / 1000;

const cat = (state: string, models: BackendModelCatalogResult["models"] = [], extra: Record<string, unknown> = {}): BackendModelCatalogResult =>
  ({ backend_id: "be-m", models, discovery: { state, fetched_at: NOW, ...extra } }) as BackendModelCatalogResult;
const found: ModelInfo[] = [{ id: "m-1", sources: ["discovered"] }, { id: "m-2", sources: ["config", "discovered"] }, { id: "m-3", sources: ["config"] }];

function mount(ui: React.ReactNode, getBackendModelCatalog: ReturnType<typeof vi.fn>, language = "ko", open = vi.fn()) {
  const { clients } = createFakeClients({ getBackendModelCatalog });
  const i18n = createTestAppI18n(language);
  // 서버 문구 묶음(실제 앱은 /i18n/{lang}에서 받는다). 코드 번역은 {reason} 자리표시자를 쓴다.
  for (const [lng, text] of [["ko", "모델 목록 실패({reason})"], ["en", "Model list failed ({reason})"]] as const) {
    applyServerCatalog(i18n, { language: lng, ns: {}, text: {}, codes: { "backend.model_discovery_failed": text } } as never);
  }
  const value = { phase: "ready" as const, summary: undefined, open };
  render(
    <AppI18nProvider i18n={i18n}>
      <QueryClientProvider client={createAppQueryClient({ retry: false })}>
        <ApiProvider clients={clients}>
          <BackendConnectContext.Provider value={value}>{ui}</BackendConnectContext.Provider>
        </ApiProvider>
      </QueryClientProvider>
    </AppI18nProvider>,
  );
  return { i18n, open };
}
const line = () => screen.findByTestId("model-catalog-form", {}, LONG);

describe("모델 칸 상태 줄 6상태", () => {
  it("가져오는 중: 응답 전에 '가져오는 중…'과 aria-busy", async () => {
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(() => new Promise(() => {})));
    const el = await line();
    expect(el.textContent).toContain("모델 목록을 가져오는 중…");
    expect(el.getAttribute("aria-busy")).toBe("true");
  });

  it("ok: 계정 출처 개수와 [새로 고침]만(연결 확인 없음)", async () => {
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("ok", found)));
    const el = await line();
    await waitFor(() => expect(el.textContent).toContain("계정에서 가져온 모델 2개"));
    expect(screen.getByRole("button", { name: "새로 고침" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "연결 확인…" })).toBeNull();
  });

  it("ok인데 계정 항목이 0개면 '가져온 모델이 없습니다'", async () => {
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("ok", [{ id: "m-3", sources: ["config"] }])));
    await waitFor(async () => expect((await line()).textContent).toContain("이 계정에서 가져온 모델이 없습니다."));
  });

  it("stale: 경고 문구 + 두 단추, [연결 확인…]은 그 백엔드를 앞으로 해서 모달을 연다", async () => {
    const { open } = mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("stale", found)));
    await waitFor(async () => expect((await line()).textContent).toContain("새로 가져오지 못했습니다"));
    expect(screen.getByRole("button", { name: "새로 고침" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "연결 확인…" }));
    expect(open).toHaveBeenCalledWith({ focusBackend: "be-m" });
  });

  it("failed: 문구 + 서버 이슈 사유(코드 번역), 두 단추", async () => {
    const issues = [{ code: "backend.model_discovery_failed", message: "server original", severity: "warning", details: { backend_id: "be-m", reason: "network" } }];
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("failed", [], { issues })));
    await waitFor(async () => expect((await line()).textContent).toContain("모델 목록을 가져오지 못했습니다."));
    expect((await line()).textContent).not.toContain("server original");
    // 앞 문구와 겹치는 서버 이슈 문장 대신 사유 코드만 짧게(앱 묶음 문구)
    expect((await line()).textContent).toContain("— 연결하지 못했습니다");
    expect((await line()).textContent).not.toContain("모델 목록 실패(");
    expect(screen.getByRole("button", { name: "연결 확인…" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "새로 고침" })).toBeTruthy();
  });

  it("failed인데 사유가 로그인 없음이면 오류가 아니라 로그인 안내(중립) + [연결 확인…]", async () => {
    const issues = [{ code: "backend.model_discovery_failed", message: "server original", severity: "warning", details: { backend_id: "be-m", reason: "auth_missing" } }];
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("failed", [], { issues })));
    await waitFor(async () => expect((await line()).textContent).toContain("로그인하면 이 계정의 모델을 가져옵니다."));
    expect((await line()).getAttribute("data-state")).toBe("signin");
    expect((await line()).textContent).not.toContain("가져오지 못했습니다");
    expect(screen.getByRole("button", { name: "연결 확인…" })).toBeTruthy();
  });

  it("failed: 모르는 사유 코드는 코드 그대로 짧게 보인다", async () => {
    const issues = [{ code: "backend.model_discovery_failed", message: "server original", severity: "warning", details: { backend_id: "be-m", reason: "zz_unknown" } }];
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("failed", [], { issues })));
    await waitFor(async () => expect((await line()).textContent).toContain("— zz_unknown"));
  });

  it("failed: 영어 사유 문구", async () => {
    const issues = [{ code: "backend.model_discovery_failed", message: "server original", severity: "warning", details: { backend_id: "be-m", reason: "timeout" } }];
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("failed", [], { issues })), "en");
    await waitFor(async () => expect((await line()).textContent).toContain("— Timed out"));
  });

  it("disabled: 문구만, 단추 없음", async () => {
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("disabled")));
    await waitFor(async () => expect((await line()).textContent).toContain("모델 자동 조회가 꺼져 있습니다."));
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("unsupported: 문구 + [연결 확인…]", async () => {
    mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("unsupported")));
    await waitFor(async () => expect((await line()).textContent).toContain("모델 목록을 가져올 수 없습니다"));
    expect(screen.getByRole("button", { name: "연결 확인…" })).toBeTruthy();
  });

  it("옛 서버(discovery null)면 줄을 그리지 않는다", async () => {
    const get = vi.fn(async () => ({ backend_id: "be-m", models: [{ id: "m-1" }], discovery: null }));
    mount(<ModelCatalogStatus backendId="be-m" />, get);
    await waitFor(() => expect(screen.queryByTestId("model-catalog-form")).toBeNull(), LONG);
    expect(get).toHaveBeenCalled();
  });

  it("[새로 고침]은 refresh=true로 부르고 결과로 줄을 바꾼다", async () => {
    const get = vi.fn(async (_id: string, o?: { refresh?: boolean }) => (o?.refresh ? cat("ok", found) : cat("failed")));
    mount(<ModelCatalogStatus backendId="be-m" />, get);
    await waitFor(async () => expect((await line()).textContent).toContain("가져오지 못했습니다"));
    fireEvent.click(screen.getByRole("button", { name: "새로 고침" }));
    await waitFor(async () => expect((await line()).textContent).toContain("계정에서 가져온 모델 2개"), LONG);
    expect(get).toHaveBeenLastCalledWith("be-m", { refresh: true });
  });

  it("화면 언어를 바꾸면 줄 문구도 바뀐다", async () => {
    const { i18n } = mount(<ModelCatalogStatus backendId="be-m" />, vi.fn(async () => cat("disabled")));
    await waitFor(async () => expect((await line()).textContent).toContain("자동 조회가 꺼져"));
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    expect((await line()).textContent).toContain("Automatic model fetching is off.");
  });

  it("모달 줄: 새로 고침만, 개수는 계정 출처 항목 수", async () => {
    mount(<ModelCatalogStatus backendId="be-m" variant="dialog" />, vi.fn(async () => cat("ok", found)));
    const el = await screen.findByTestId("model-catalog-dialog", {}, LONG);
    await waitFor(() => expect(el.textContent).toContain("이 계정에서 쓸 수 있는 모델 2개"));
    expect(screen.queryByRole("button", { name: "연결 확인…" })).toBeNull();
  });

  it("refetchKey가 바뀌면 다시 읽는다(로그인 성공 뒤 자동 새로 고침)", async () => {
    const get = vi.fn(async () => cat("ok", found));
    const { rerender } = (() => {
      const { clients } = createFakeClients({ getBackendModelCatalog: get });
      const i18n = createTestAppI18n("ko");
      const qc = createAppQueryClient({ retry: false });
      const tree = (key: number) => (
        <AppI18nProvider i18n={i18n}>
          <QueryClientProvider client={qc}>
            <ApiProvider clients={clients}>
              <ModelCatalogStatus backendId="be-m" variant="dialog" refetchKey={key} />
            </ApiProvider>
          </QueryClientProvider>
        </AppI18nProvider>
      );
      const r = render(tree(1));
      return { rerender: (k: number) => r.rerender(tree(k)) };
    })();
    await screen.findByTestId("model-catalog-dialog", {}, LONG);
    const before = get.mock.calls.length;
    rerender(2);
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(before), LONG);
  });
});

describe("모델 칸 옵션", () => {
  const widget = (models: BackendModelCatalogResult["models"], overrides: Partial<ModelOptions> = {}) => {
    const options: ModelOptions = {
      models: models ?? [],
      failed: false,
      emptyLabel: "(지정 안 함)",
      customLabel: "직접 입력",
      failedNote: "실패",
      backendId: "be-m",
      sourceLabel: (m) => (m.sources ?? []).map((s) => (s === "config" ? "설정" : "계정")).join(" / "),
      sourceTip: () => "",
      ...overrides,
    };
    const props = { id: "f", value: null, onChange: vi.fn(), onBlur: vi.fn(), label: "모델", options, errors: [], disabled: false, readonly: false } as unknown as SchemaFormWidgetProps;
    return <ModelWidget {...props} />;
  };

  it("설정 목록이 비어도 조회한 목록이 옵션이 되고, 옵션에 출처 표시가 붙는다", async () => {
    mount(widget(found), vi.fn(async () => cat("ok", found)));
    const select = await screen.findByLabelText("모델");
    const texts = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(texts).toEqual(["(지정 안 함)", "m-1 — 계정", "m-2 — 설정 / 계정", "m-3 — 설정", "직접 입력"]);
  });

  it("조회가 failed여도 직접 입력으로 바꿔 값을 쓸 수 있다", async () => {
    mount(widget([{ id: "m-3", sources: ["config"] }]), vi.fn(async () => cat("failed")));
    const select = await screen.findByLabelText("모델");
    fireEvent.change(select, { target: { value: "\u0000custom" } });
    expect(await screen.findByRole("textbox", { name: "직접 입력" })).toBeTruthy();
  });
});
