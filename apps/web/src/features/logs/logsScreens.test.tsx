import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { LogEvent, LogSessionSummary, LogSourceInfo, LogTimeline, WorkspaceSettings } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createFakeClients } from "../../testing/fakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

// 화면은 지연 로딩이고 느린 파일시스템이라 기본 1초 대기로는 모자란다.
const LONG = { timeout: 15_000 };

// 출처·범주·모델 이름은 모두 임의 값이다. 앱은 이 이름을 모른다.
const src = (id: string, over: Partial<LogSourceInfo> & { reads?: boolean; def?: boolean } = {}): LogSourceInfo => ({
  descriptor: { id, title: `출처-${id}`, format: "fmt", reads_paths: over.reads ?? false, default_enabled: over.def ?? false, description: `${id} 설명`, config_schema: { type: "object", properties: { roots: { type: "array", items: { type: "string" }, title: "읽는 위치" } } } },
  enabled: over.enabled ?? false,
  origin: "plugin",
  ...(over.status ? { status: over.status } : {}),
});
const session = (id: string): LogSessionSummary => ({ session: id, first_time: 1_700_000_000, last_time: 1_700_000_100, events: 3, errors: 1, thread_count: 2, models: ["m-1"], tokens: { total: 4100 } });
const event = (n: number, over: Partial<LogEvent> = {}): LogEvent => ({ uid: `u${n}`, seq: n, source: "x", observed_at: n, category: n === 2 ? "cat-err" : "cat-a", title: `이벤트 ${n}`, time: 1_700_000_000 + n, thread: n === 3 ? "th-2" : "th-1", ...over });
const timeline = (): LogTimeline => ({ session: session("ses-1"), lanes: [{ id: "th-1", label: "메인 줄" }, { id: "th-2", label: "서브 줄" }], events: [event(1), event(2), event(3, { duration_ms: 1500 })], total: 3 });

function mount(path: string, rest: Record<string, unknown> = {}, settings: WorkspaceSettings = {}) {
  const { clients, ws } = createFakeClients({
    getSettingsVersioned: async () => ({ value: settings, version_hash: "s1" }),
    getLogTaxonomy: async () => ({ categories: { "cat-err": { label: "오류범주", tone: "danger" } } }),
    getLogSchema: async () => {
      throw new ApiError(404, { code: "not_found", message: "없음" });
    },
    listLogSources: async () => [src("a", { enabled: true })],
    ...rest,
  });
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { clients, ws, router };
}

describe("로그: 세션 목록", () => {
  it("예약 파라미터(range)는 서버 요청에 실리지 않고 정렬은 항상 명시된다", async () => {
    const calls: Record<string, unknown>[] = [];
    mount("/logs/sessions?range=all&model=m-1", { listLogSessions: async (p: Record<string, unknown>) => (calls.push(p), [session("ses-1")]) });
    await screen.findByRole("grid", { name: "세션 목록" }, LONG);
    expect(calls[0]).toMatchObject({ order: "desc", limit: "200", model: "m-1" });
    expect(calls[0]).not.toHaveProperty("range");
    expect(calls[0]).not.toHaveProperty("since");
  });

  it("켜진 출처가 없으면 첫 사용 카드, 카드의 출처는 서버 디스크립터에서만 온다(읽는 출처 먼저)", async () => {
    mount("/logs/sessions", { listLogSources: async () => [src("p"), src("q", { reads: true })], listLogSessions: async () => [] });
    const card = await screen.findByTestId("logs-first-use", {}, LONG);
    const titles = Array.from(card.querySelectorAll(".logs-source-cards > li")).map((li) => li.textContent ?? "");
    expect(titles[0]).toContain("출처-q");
    expect(within(card).getAllByText("원본은 읽기만 함")).toHaveLength(1);
    expect(card.textContent).toContain("대화 원문이 포함될 수 있고");
  });

  it("목록이 비면 필터 없는 limit=1 조회로 B(수집된 로그 없음)와 C(조건 불일치)를 가르고, 조회 실패는 C", async () => {
    const probe: Record<string, unknown>[] = [];
    mount("/logs/sessions", { listLogSessions: async () => [], listLogEvents: async (p: Record<string, unknown>) => (probe.push(p), { items: [] }) });
    await screen.findByTestId("logs-empty-b", {}, LONG);
    expect(probe[0]).toEqual({ limit: 1 });
    cleanup();
    mount("/logs/sessions", { listLogSessions: async () => [], listLogEvents: async () => { throw new ApiError(500, { code: "x", message: "실패" }); } });
    await screen.findByTestId("logs-empty-c", {}, LONG);
  });

  it("서버 422(details.path)는 해당 필터 칩에 표시되고 이전 결과가 있으면 유지된다", async () => {
    let n = 0;
    mount("/logs/sessions?range=all&model=bad", {
      listLogSessions: async () => {
        if (n++ === 0) throw new ApiError(422, { code: "validation_failed", message: "모델 값이 틀렸습니다", details: { path: "filter.model" } });
        return [];
      },
    });
    const chip = await screen.findByRole("button", { name: /모델: bad/ }, LONG);
    await waitFor(() => expect(chip.getAttribute("aria-invalid")).toBe("true"), LONG);
    expect(screen.getAllByText(/모델 값이 틀렸습니다/).length).toBeGreaterThan(0);
  });
});

describe("로그: 세션 상세", () => {
  it("세션에 나온 범주 전부를 칩으로 보이고 선택은 URL에 반영되며, 응답 대기 서버 값만 쓴다", async () => {
    const { router } = mount("/logs/sessions/ses-1", { getLogTimeline: async () => timeline() });
    const chips = await screen.findByRole("group", { name: "범주 필터" }, LONG);
    expect(await within(chips).findByRole("button", { name: /오류범주/ }, LONG)).toBeTruthy();
    expect(within(chips).getByRole("button", { name: /cat-a/ })).toBeTruthy();
    fireEvent.click(within(chips).getByRole("button", { name: /오류범주/ }));
    await waitFor(() => expect(router.state.location.search).toContain("category=cat-err"));
    expect(router.state.location.search).not.toContain("through");
  });

  it("없는 세션(404)은 안내와 목록 링크", async () => {
    mount("/logs/sessions/none", { getLogTimeline: async () => { throw new ApiError(404, { code: "not_found", message: "x" }); } });
    expect(await screen.findByText("세션을 찾을 수 없습니다", {}, LONG)).toBeTruthy();
  });

  it("재생 위치 키보드 이동: 스크러버 ←는 한 이벤트 줄이고 URL through가 생긴다", async () => {
    const { router } = mount("/logs/sessions/ses-1", { getLogTimeline: async () => timeline() });
    const slider = await screen.findByRole("slider", {}, LONG);
    await waitFor(() => expect(slider.getAttribute("aria-valuenow")).toBe("3"), LONG);
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    await waitFor(() => expect(slider.getAttribute("aria-valuenow")).toBe("2"), LONG);
    await waitFor(() => expect(router.state.location.search).toContain("through=2"), LONG);
  });
});

describe("로그: 검색", () => {
  it("handoff 셀 클릭은 from·to 필터를 더해 이벤트 보기로 전환한다", async () => {
    const { router } = mount("/logs/search?view=handoff&range=all", { getLogHandoffs: async () => ({ cells: [{ source: "pl", target: "be", count: 7, from: "pl", to: "be" }] }) });
    const cell = await screen.findByRole("button", { name: /pl에서 be로 7회/ }, LONG);
    fireEvent.click(cell);
    await waitFor(() => expect(router.state.location.search).toContain("from=pl"), LONG);
    expect(router.state.location.search).toContain("to=be");
    expect(router.state.location.search).not.toContain("view=");
  });
});

describe("로그: 대시보드", () => {
  it("대시보드가 없으면 빈 상태, 템플릿이 0개여도 빈 대시보드를 만들 수 있다", async () => {
    mount("/logs/dashboards", { listLogDashboardTemplates: async () => [] });
    await screen.findByTestId("logs-dash-empty", {}, LONG);
    fireEvent.click(screen.getByRole("button", { name: "빈 대시보드 만들기" }));
    await screen.findByRole("button", { name: "저장" }, LONG);
  });

  it("알 수 없는 위젯 종류는 자리 표시로 그리고 집계 요청을 보내지 않는다", async () => {
    const aggregate: unknown[] = [];
    mount(
      "/logs/dashboards/d1",
      { aggregateLogs: async (r: unknown) => (aggregate.push(r), []) },
      { logs: { dashboards: [{ id: "d1", title: "대시", widgets: [{ id: "w1", kind: "kind-zzz", query: { metric: "m" }, options: {} }] }] } },
    );
    await screen.findByText(/알 수 없는 위젯 \(kind-zzz\)/, {}, LONG);
    expect(aggregate).toEqual([]);
  });
});

describe("로그: 기능 꺼짐", () => {
  it("logs 역할이 없으면 사이드바에 로그가 없고 직접 주소는 꺼진 기능 안내이며 로그 요청이 없다", async () => {
    const calls: string[] = [];
    mount("/logs/sessions", {
      listModules: async () => [{ id: "m-x", kind: "k-any", version: "0.0.1", status: "disabled", web_roles: ["logs"] }],
      listLogSessions: async () => (calls.push("s"), []),
      listLogSources: async () => (calls.push("src"), []),
    });
    await screen.findByRole("heading", { name: "이 기능은 꺼져 있습니다" }, LONG);
    expect(screen.queryByRole("link", { name: /^로그/ })).toBeNull();
    expect(calls).toEqual([]);
  });
});
