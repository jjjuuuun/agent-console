import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES, type ArchitectureView, type LogEvent, type LogTimeline, type ModuleInfo } from "@agent-console/contracts";
import { sampleCell, sampleEdge } from "@agent-console/arch-view/testing";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createFakeClients } from "../../testing/fakes";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

const LONG = { timeout: 20_000 };

// 칸·묶음·레인·역할 이름은 모두 임의 값이다. 앱은 이 이름을 모른다.
const obs = (value: number) => ({ status: "observed" as const, value });
const event = (n: number, thread: string): LogEvent => ({ uid: `u${n}`, seq: n, source: "x", observed_at: n, category: "cat-a", title: `이벤트 ${n}`, time: 1_700_000_000 + n, thread });
const events = [event(1, "th-1"), event(2, "th-1"), event(3, "th-2")];
const timeline = (): LogTimeline => ({
  session: { session: "ses-1", first_time: 1_700_000_000, last_time: 1_700_000_100, events: 3, errors: 0, thread_count: 2 },
  lanes: [{ id: "th-1", label: "메인 줄" }, { id: "th-2", label: "서브 줄" }],
  events,
  total: 3,
});
const archView = (over: Partial<ArchitectureView> = {}): ArchitectureView => ({
  profile: "pf-1",
  title: "임의 프로필",
  event_total: 3,
  max_seq: 3,
  cells: [
    sampleCell("zz1", {
      label: "칸가", x: 100, y: 60, metrics: { count: obs(2) }, selector: { arch: "pf-1:cell:zz1" }, drillable: true,
      groups: [{ key: "k1", label: "묶음하나", metrics: { count: obs(2) }, selector: { arch: "pf-1:cell:zz1", arch_group: "k1" }, drill: { filter: "thread", value: "th-2" } }],
    }),
    sampleCell("zz2", { label: "칸나", x: 340, y: 60, status: "not_collected", metrics: { count: { status: "not_collected", value: null } } }),
    sampleCell("zz3", { label: "칸다", x: 580, y: 60, metrics: { count: obs(1) }, selector: { arch: "pf-1:cell:zz3" } }),
  ],
  edges: [sampleEdge("ee1", "zz1", "zz3", { label: "연결가", metrics: { count: obs(1) } })],
  ...over,
});

const mod = (roles: string[]): ModuleInfo => ({ id: "m-any", kind: "k-any", version: "0.0.1", status: "active", web_roles: roles });

function mount(path: string, roles: string[], rest: Record<string, unknown> = {}) {
  const base: Record<string, (...args: never[]) => unknown> = {
    listModules: async () => [mod(roles)],
    getSettingsVersioned: async () => ({ value: {}, version_hash: "s1" }),
    getLogTaxonomy: async () => ({ categories: {} }),
    getLogSchema: async () => {
      throw new ApiError(404, { code: "not_found", message: "없음" });
    },
    listLogSources: async () => [],
    getLogTimeline: async () => timeline(),
    listArchitectureProfiles: async () => ({ profiles: [{ id: "pf-1", title: "임의 프로필", origin: "user" }], default_profile: "pf-1" }),
    getLogArchitecture: async () => archView(),
    getLogEventArchitecture: async () => ({ profile: "pf-1", uid: "u1", cells: ["zz3"], edges: [] }),
    listLogEvents: async () => ({ items: events.slice(0, 2) }),
    ...(rest as Record<string, (...args: never[]) => unknown>),
  };
  const { clients, ws, rest: mocks } = createFakeClients(Object.fromEntries(Object.entries(base).map(([k, f]) => [k, vi.fn(f)])));
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { clients, ws, mocks, router };
}
const openArch = async () => {
  fireEvent.click(await screen.findByRole("button", { name: "구조도" }, LONG));
  return screen.findByRole("region", { name: "구조도" }, LONG);
};

describe("세션 상세 [구조도] 세그먼트", () => {
  it("역할 logs:architecture가 없으면 세그먼트가 없고 구조도 API를 부르지 않는다", async () => {
    const { mocks } = mount("/logs/sessions/ses-1", ["logs", "logs:trace"]);
    await screen.findByRole("group", { name: "흐름 보기" }, LONG);
    expect(screen.queryByRole("button", { name: "구조도" })).toBeNull();
    expect(mocks["getLogArchitecture"]).not.toHaveBeenCalled();
    expect(mocks["listArchitectureProfiles"]).not.toHaveBeenCalled();
  });

  it("세그먼트를 처음 열기 전에는 질의하지 않고, 열면 범위(세션·레인)로 질의한다", async () => {
    const { mocks } = mount("/logs/sessions/ses-1", ["logs", "logs:architecture"]);
    const btn = await screen.findByRole("button", { name: "구조도" }, LONG);
    expect(mocks["getLogArchitecture"]).not.toHaveBeenCalled();
    fireEvent.click(btn);
    await screen.findByRole("region", { name: "구조도" }, LONG);
    expect(mocks["getLogArchitecture"]).toHaveBeenCalledTimes(1);
    expect(mocks["getLogArchitecture"]!.mock.calls[0]![0]).toMatchObject({ session: "ses-1" });
  });

  it("목록의 칸 행 수 = 뷰의 칸 수, 연결 행 수 = 연결 수 (이름은 데이터에서만)", async () => {
    mount("/logs/sessions/ses-1", ["logs", "logs:architecture"]);
    const panel = await openArch();
    const cells = await within(panel).findByRole("list", { name: "칸 3" }, LONG);
    expect(within(cells).getAllByRole("button")).toHaveLength(3);
    expect(within(within(panel).getByRole("list", { name: "연결 1" })).getAllByRole("button")).toHaveLength(1);
  });

  it("칸을 누르면 구조도 칩 하나가 생기고 서버에 arch·max_seq·세션이 실려 표가 걸러진다; 같은 칸을 다시 누르면 풀린다", async () => {
    const { mocks } = mount("/logs/sessions/ses-1", ["logs", "logs:architecture"]);
    const panel = await openArch();
    fireEvent.click(await within(panel).findByRole("button", { name: /^칸가/ }, LONG));
    await screen.findByText("구조도: 칸가", {}, LONG);
    await waitFor(() => expect(mocks["listLogEvents"]).toHaveBeenCalled(), LONG);
    expect(mocks["listLogEvents"]!.mock.calls.at(-1)![0]).toMatchObject({ session: "ses-1", arch: "pf-1:cell:zz1", max_seq: 3, order: "asc" });
    // 표 수 = 칸의 횟수(2)
    await screen.findByText("구조도 칸가 2건", {}, LONG);
    const table = await screen.findByRole("grid", { name: "이벤트 표" }, LONG);
    await waitFor(() => expect(within(table).queryByText("이벤트 3")).toBeNull(), LONG);
    expect(within(table).getByText("이벤트 2")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: /^칸가/ }));
    await waitFor(() => expect(screen.queryByText("구조도: 칸가")).toBeNull());
    expect(screen.queryByText(/^구조도 칸가/)).toBeNull();
  });

  it("관측값이 0건인 칸을 누르면 표 자리에 0건 문구가 보인다", async () => {
    mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], {
      getLogArchitecture: async () => archView({ cells: [sampleCell("zz9", { label: "빈칸", x: 100, y: 60, metrics: { count: obs(0) }, selector: { arch: "pf-1:cell:zz9" } })], edges: [] }),
      listLogEvents: async () => ({ items: [] }),
    });
    const panel = await openArch();
    fireEvent.click(await within(panel).findByRole("button", { name: /^빈칸/ }, LONG));
    await screen.findByText("구조도 빈칸 0건이라 걸러낼 이벤트가 없습니다", {}, LONG);
  });

  it("수집 안 됨 칸은 필터가 걸리지 않고 안내 토스트만 뜬다", async () => {
    const { mocks } = mount("/logs/sessions/ses-1", ["logs", "logs:architecture"]);
    const panel = await openArch();
    fireEvent.click(await within(panel).findByRole("button", { name: /^칸나/ }, LONG));
    await screen.findByText("수집 안 됨 칸은 걸러낼 이벤트가 없습니다.", {}, LONG);
    expect(screen.queryByText("구조도: 칸나")).toBeNull();
    expect(mocks["listLogEvents"]).not.toHaveBeenCalled();
  });

  it("서버가 거절하면(422) 칩이 남지 않고 서버 메시지 토스트가 뜬다", async () => {
    mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], {
      listLogEvents: async () => {
        throw new ApiError(422, { code: "validation_failed", message: "모르는 구조도 이름입니다" });
      },
    });
    const panel = await openArch();
    fireEvent.click(await within(panel).findByRole("button", { name: /^칸다/ }, LONG));
    await screen.findByText("모르는 구조도 이름입니다", {}, LONG);
    await waitFor(() => expect(screen.queryByText("구조도: 칸다")).toBeNull());
    expect(screen.getByRole("list", { name: "칸 3" })).toBeTruthy(); // 그림은 유지
  });

  it("하위 구조도 왕복: 묶음으로 들어가면 필터와 빵 부스러기가 더해지고, 처음으로 돌아가면 사라진다", async () => {
    const { mocks } = mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], {
      getLogArchitecture: async (p: Record<string, unknown>) => (p["thread"] && (p["thread"] as string[]).length > 0 ? archView({ title: "하위", event_total: 1 }) : archView()),
    });
    const panel = await openArch();
    fireEvent.click(await within(panel).findByRole("button", { name: /^칸가/ }, LONG)); // 정보 줄에 묶음 칩이 나온다
    fireEvent.doubleClick(await screen.findByRole("button", { name: /묶음하나/ }, LONG));
    await waitFor(() => expect(mocks["getLogArchitecture"]!.mock.calls.at(-1)![0]).toMatchObject({ thread: ["th-2"] }), LONG);
    await screen.findByRole("group", { name: "구조도: 하위" }, LONG);
    const crumbs = await screen.findByRole("navigation", { name: "구조도 위치" });
    expect(within(crumbs).getByText("묶음하나").getAttribute("aria-current")).toBe("page");
    expect(screen.getByText("thread: 묶음하나")).toBeTruthy(); // 필터 줄의 단계 칩
    // 처음으로
    fireEvent.click(within(crumbs).getByRole("button", { name: "세션" }));
    await waitFor(() => expect(screen.queryByText("thread: 묶음하나")).toBeNull());
    await screen.findByRole("group", { name: "구조도: 임의 프로필" }, LONG); // 처음 범위의 그림(캐시)으로 돌아온다
    expect(within(await screen.findByRole("navigation", { name: "구조도 위치" })).queryByRole("button")).toBeNull();
  });

  it("빈 상태: 규칙 없음(A)은 안내 블록, 상한 초과(D)는 서버 수치를 쓰며 레인 세그먼트는 그대로 쓸 수 있다", async () => {
    mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], {
      getLogArchitecture: async () => {
        throw new ApiError(404, { code: ERROR_CODES.ARCHITECTURE_PROFILE_NOT_FOUND, message: "프로필 없음" });
      },
    });
    await openArch();
    await screen.findByText("구조도 규칙이 없습니다", {}, LONG);
    expect(screen.getByRole("button", { name: "설정 열기" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "레인" }));
    expect(screen.queryByText("구조도 규칙이 없습니다")).toBeNull();
    cleanup();
    mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], {
      getLogArchitecture: async () => {
        throw new ApiError(422, { code: ERROR_CODES.ARCHITECTURE_SCOPE_TOO_LARGE, message: "큼", details: { events: 90_000, limit: 50_000 } });
      },
    });
    await openArch();
    await screen.findByText("범위가 너무 큽니다", {}, LONG);
    expect(screen.getByText(/90,000건으로 구조도 상한\(50,000\)/)).toBeTruthy();
  });

  it("규칙(프로필)이 하나도 없으면 구조도를 요청하지 않고(404 콘솔 오류 없음) 규칙 없음 안내를 보인다", async () => {
    const { mocks } = mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], {
      listArchitectureProfiles: async () => ({ profiles: [], default_profile: null }),
    });
    await openArch();
    await screen.findByText("구조도 규칙이 없습니다", {}, LONG);
    expect(mocks["getLogArchitecture"]).not.toHaveBeenCalled();
  });

  it("빈 상태: 이벤트 0건(B)은 칸을 그대로 그리고 모든 칸 수집 안 됨(C)은 출처 종류를 알린다", async () => {
    mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], { getLogArchitecture: async () => archView({ event_total: 0 }) });
    await openArch();
    await screen.findByText("이 범위에 이벤트가 없습니다", {}, LONG);
    expect(screen.getByRole("list", { name: "칸 3" })).toBeTruthy();
    cleanup();
    const dead = { status: "not_collected" as const, value: null };
    mount("/logs/sessions/ses-1", ["logs", "logs:architecture"], {
      getLogArchitecture: async () => archView({ cells: [sampleCell("a1", { status: "not_collected", metrics: { count: dead } })], edges: [], sources: [{ id: "s1", kind: "kind-z", events: 4 }] }),
    });
    await openArch();
    await screen.findByText("어떤 칸도 채울 수 없습니다", {}, LONG);
    expect(screen.getByText(/kind-z/)).toBeTruthy();
  });

  it("logs.ingested가 오면 1초 디바운스 뒤 다시 질의하고 선택은 그대로다", async () => {
    const { mocks, ws } = mount("/logs/sessions/ses-1", ["logs", "logs:architecture"]);
    const panel = await openArch();
    fireEvent.click(await within(panel).findByRole("button", { name: /^칸다/ }, LONG));
    await screen.findByText("구조도: 칸다", {}, LONG);
    const before = mocks["getLogArchitecture"]!.mock.calls.length;
    ws.emitLogs(2);
    ws.emitLogs(3);
    await waitFor(() => expect(mocks["getLogArchitecture"]!.mock.calls.length).toBe(before + 1), { timeout: 8000 });
    expect(screen.getByText("구조도: 칸다")).toBeTruthy();
  });

  it("표에서 이벤트를 고르면 그 이벤트의 membership으로 칸이 강조된다", async () => {
    const { mocks } = mount("/logs/sessions/ses-1?x=1#e=u1", ["logs", "logs:architecture"]);
    await openArch();
    await waitFor(() => expect(mocks["getLogEventArchitecture"]).toHaveBeenCalledWith("u1", "pf-1"), LONG);
    const row = await screen.findByRole("button", { name: /^칸다.*선택한 이벤트가 지나감/ }, LONG);
    expect(row.getAttribute("data-highlighted")).toBe("");
  });
});
