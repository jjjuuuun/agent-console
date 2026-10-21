import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BackendDescriptor, BackendProbeResult, BackendReadiness } from "@agent-console/contracts";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { StorageProvider } from "../../app/StorageContext";
import { createSafeStorage } from "../../app/storage";
import { createFakeClients } from "../../testing/fakes";
import { ConnectedBackendChooserCard } from "../backendChoice";
import { BackendReadinessSection } from "./BackendReadinessSection";
import { resolveTone } from "./tones";

afterEach(cleanup);

// 백엔드 id·상태 문구는 전부 임의 값이다(화면 코드는 모른다).
const NOW = Date.now() / 1000;
const supported = { id: "be-a", title: "백엔드 에이", cost_note: "비용 일반 안내", probe_cost_note: "테스트 비용 안내", capabilities: { status: true, probe: true } } as BackendDescriptor;
const plain = { id: "be-b", title: "백엔드 비", capabilities: { status: false, probe: false } } as BackendDescriptor;
const statuses: BackendReadiness[] = [
  { backend_id: "be-a", state: "zz_state", tone: "error", summary: "서버가 준 문구 A", short_summary: "짧음A", detail: "자세한 설명", checked_at: NOW, fixes: [{ label: "고치러 가기", target: { role: "no-role" } }], checks: [{ id: "c1", title: "항목 하나", ok: false, note: "없음" }] },
  { backend_id: "be-b", state: "unknown", tone: "mystery" as never, summary: "", checked_at: NOW },
];
const okProbe: BackendProbeResult = { backend_id: "be-a", ok: true, latency_ms: 1200, message: "", details: { model: "m-1" }, finished_at: NOW };
const badProbe: BackendProbeResult = { backend_id: "be-a", ok: false, reason: "zz_reason", message: "서버가 준 실패 문장", fixes: [], finished_at: NOW };

function setup(node: (backends: BackendDescriptor[]) => React.ReactNode, overrides: Record<string, unknown> = {}) {
  const { clients, rest } = createFakeClients({ listBackendStatuses: vi.fn(async () => statuses), getBackendStatus: vi.fn(async () => statuses[0]), probeBackend: vi.fn(async () => okProbe), ...overrides });
  const mem = new Map<string, string>();
  const storage = createSafeStorage({ getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v), removeItem: (k: string) => void mem.delete(k), key: (i: number) => [...mem.keys()][i] ?? null, get length() { return mem.size; }, clear: () => mem.clear() } as Storage);
  const router = createMemoryRouter([{ path: "*", element: node([supported, plain]) }], { initialEntries: ["/x"] });
  render(
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>
        <StorageProvider storage={storage}>
          <RouterProvider router={router} />
        </StorageProvider>
      </ApiProvider>
    </QueryClientProvider>,
  );
  return { rest, storage };
}

describe("resolveTone", () => {
  it("모르는 톤은 unknown", () => {
    expect(resolveTone("mystery")).toBe("unknown");
    expect(resolveTone("error")).toBe("error");
    expect(resolveTone(undefined)).toBe("unknown");
  });
});

describe("BackendReadinessSection", () => {
  it("서버가 준 문구·세부 항목을 그리고, 확인 불가·미지원 백엔드는 테스트 버튼이 없다", async () => {
    const { rest } = setup((b) => <BackendReadinessSection backends={b} />);
    expect(await screen.findByText("서버가 준 문구 A")).toBeTruthy();
    expect(screen.getByText("자세한 설명")).toBeTruthy();
    expect(screen.getByText("비용 일반 안내")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "연결 테스트" })).toHaveLength(1);
    expect(screen.getByText("이 백엔드는 연결 테스트를 지원하지 않습니다")).toBeTruthy();
    expect(screen.getAllByText("확인할 수 없음").length).toBeGreaterThan(0);
    expect(rest.probeBackend).not.toHaveBeenCalled();
  });

  it("[연결 테스트]는 확인 다이얼로그 전에 호출하지 않고, 비용 안내를 보인다", async () => {
    const { rest } = setup((b) => <BackendReadinessSection backends={b} />);
    fireEvent.click(await screen.findByRole("button", { name: "연결 테스트" }));
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByTestId("probe-cost-note").textContent).toBe("테스트 비용 안내");
    expect(rest.probeBackend).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(rest.probeBackend).not.toHaveBeenCalled();
  });

  it("[테스트 실행] 뒤 호출하고 성공 결과(소요 시간·확인 정보)를 보인다", async () => {
    const { rest } = setup((b) => <BackendReadinessSection backends={b} />);
    fireEvent.click(await screen.findByRole("button", { name: "연결 테스트" }));
    fireEvent.click(await screen.findByRole("button", { name: "테스트 실행" }));
    expect(await screen.findByText("연결됨 — 응답 1.2초")).toBeTruthy();
    expect(screen.getByText("model: m-1")).toBeTruthy();
    expect(screen.getByText("테스트 통과")).toBeTruthy();
    expect(rest.probeBackend).toHaveBeenCalledTimes(1);
    expect(rest.probeBackend).toHaveBeenCalledWith("be-a");
  });

  it("다음부터 묻지 않기를 체크하면 다음엔 바로 실행한다", async () => {
    const { rest, storage } = setup((b) => <BackendReadinessSection backends={b} />);
    fireEvent.click(await screen.findByRole("button", { name: "연결 테스트" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "다음부터 묻지 않기" }));
    fireEvent.click(screen.getByRole("button", { name: "테스트 실행" }));
    await waitFor(() => expect(rest.probeBackend).toHaveBeenCalledTimes(1));
    expect(storage.get("ac.backend.probe.confirmed.be-a")).toBe("1");
    fireEvent.click(await screen.findByRole("button", { name: "연결 테스트" }));
    await waitFor(() => expect(rest.probeBackend).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("실패는 사유 문장과 접힌 상세(사유 코드)를 보인다", async () => {
    setup((b) => <BackendReadinessSection backends={b} />, { probeBackend: vi.fn(async () => badProbe) });
    fireEvent.click(await screen.findByRole("button", { name: "연결 테스트" }));
    fireEvent.click(await screen.findByRole("button", { name: "테스트 실행" }));
    expect(await screen.findByText("서버가 준 실패 문장")).toBeTruthy();
    expect(screen.getByText(/사유 코드: zz_reason/)).toBeTruthy();
    expect(screen.queryByText("테스트 통과")).toBeNull();
  });

  it("[다시 확인]은 그 백엔드 상태만 다시 읽는다(폴링 없음)", async () => {
    const { rest } = setup((b) => <BackendReadinessSection backends={b} />);
    await screen.findByText("서버가 준 문구 A");
    expect(rest.listBackendStatuses).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByRole("button", { name: "다시 확인" })[0] as HTMLElement);
    await waitFor(() => expect(rest.getBackendStatus).toHaveBeenCalledWith("be-a"));
    expect(rest.listBackendStatuses).toHaveBeenCalledTimes(1);
  });

  it("상태 API가 404(모듈 꺼짐)면 아무것도 그리지 않는다", async () => {
    const { ApiError } = await import("@agent-console/api-client");
    setup((b) => <BackendReadinessSection backends={b} />, { listBackendStatuses: vi.fn(async () => { throw new ApiError(404, { code: "not_found", message: "없음" }); }) });
    await waitFor(() => expect(screen.queryByTestId("backend-readiness-section")).toBeNull());
    expect(screen.queryByText(/확인하지 못했습니다/)).toBeNull();
  });
});

describe("ConnectedBackendChooserCard", () => {
  it("항목마다 상태 칩이 있고, error 항목을 골라도 선택은 막히지 않으며 경고가 보인다", async () => {
    const { rest } = setup((b) => <ConnectedBackendChooserCard options={b} onConfirm={() => {}} />);
    await waitFor(() => expect(screen.getAllByTestId("backend-status-chip").length).toBe(2));
    expect(screen.getByText("짧음A")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /백엔드 에이/ }));
    expect(await screen.findByTestId("backend-chooser-warn")).toBeTruthy();
    expect((screen.getByRole("button", { name: /선택하고 계속/ }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole("button", { name: "연결 테스트" })).toBeTruthy();
    expect(rest.probeBackend).not.toHaveBeenCalled();
  });
});
