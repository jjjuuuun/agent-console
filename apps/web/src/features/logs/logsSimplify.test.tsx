import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { LogEvent, LogSessionSummary, LogSourceInfo, LogTimeline, WorkspaceSettings } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createFakeClients } from "../../testing/fakes";
import { ActionMenu, type ActionMenuEntry } from "./ActionMenu";
import { NoticeBar, sortNotices, type LogNotice } from "./NoticeBar";
import { viewMenuEntries } from "./LogViewMenu";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);
const LONG = { timeout: 15_000 };

describe("NoticeBar(5.7R.32 AC-5)", () => {
  const n = (id: string, priority: number, extra: Partial<LogNotice> = {}): LogNotice => ({ id, priority, tone: "info", text: `알림-${id}`, ...extra });
  it("우선순위가 높은 알림 하나만 줄에 보이고 안정 정렬이다", () => {
    expect(sortNotices([n("b", 4), n("a", 1), n("c", 4)]).map((x) => x.id)).toEqual(["a", "b", "c"]);
  });
  it("알림이 0개면 아무것도 그리지 않는다(세로 공간 0)", () => {
    const { container } = render(<NoticeBar notices={[]} />);
    expect(container.firstChild).toBeNull();
  });
  it("3개면 최우선 1개와 '외 2건'만 보이고, 팝오버에 나머지 둘이 각자 버튼·닫기와 함께 있다", () => {
    const act = vi.fn();
    const dismiss = vi.fn();
    render(<NoticeBar notices={[n("low", 5, { onDismiss: dismiss }), n("top", 1), n("mid", 4, { action: { label: "불러오기", onClick: act } })]} />);
    const bar = screen.getByTestId("logs-noticebar");
    expect(bar.getAttribute("role")).toBe("status");
    expect(bar.getAttribute("aria-live")).toBe("polite");
    expect(within(bar).getByText("알림-top")).toBeTruthy();
    expect(within(bar).queryByText("알림-mid")).toBeNull();
    const more = screen.getByRole("button", { name: /외 2건/ });
    expect(more.getAttribute("aria-haspopup")).toBe("dialog");
    fireEvent.click(more);
    const pop = screen.getByRole("dialog", { name: "모두 보기" });
    expect(within(pop).getByText("알림-mid")).toBeTruthy();
    expect(within(pop).getByText("알림-low")).toBeTruthy();
    fireEvent.click(within(pop).getByRole("button", { name: "불러오기" }));
    expect(act).toHaveBeenCalled();
    fireEvent.click(within(pop).getByRole("button", { name: "안내 닫기" }));
    expect(dismiss).toHaveBeenCalled();
    fireEvent.keyDown(pop, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "모두 보기" })).toBeNull();
    expect(document.activeElement).toBe(more);
  });
  it("알림이 하나면 '외 n건'이 없다", () => {
    render(<NoticeBar notices={[n("only", 3)]} />);
    expect(screen.queryByRole("button", { name: /외/ })).toBeNull();
  });
});

describe("ActionMenu(5.7R.32 AC-8)", () => {
  const entries = (onPick: () => void, onCheck: (v: boolean) => void): ActionMenuEntry[] => [
    { kind: "item", id: "a", label: "첫 항목", onSelect: onPick },
    { kind: "check", id: "c", label: "체크 항목", checked: true, onChange: onCheck },
    { kind: "heading", id: "h", label: "묶음" },
    { kind: "radio", id: "r1", label: "라디오 하나", checked: false, onSelect: () => undefined },
    { kind: "radio", id: "r2", label: "라디오 둘", checked: true, onSelect: () => undefined },
  ];
  it("키보드만으로 열고(↓), 첫 항목에 포커스, ↑↓로 이동, Esc로 닫으면 단추로 돌아오며 aria-checked가 상태와 같다", () => {
    const onCheck = vi.fn();
    render(<ActionMenu label="메뉴" trigger="⋯" triggerLabel="더 보기" entries={entries(() => undefined, onCheck)} />);
    const trigger = screen.getByRole("button", { name: "더 보기" });
    expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const menu = screen.getByRole("menu", { name: "메뉴" });
    expect(document.activeElement).toBe(within(menu).getByRole("menuitem", { name: /첫 항목/ }));
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "ArrowDown" });
    const check = within(menu).getByRole("menuitemcheckbox", { name: "체크 항목" });
    expect(document.activeElement).toBe(check);
    expect(check.getAttribute("aria-checked")).toBe("true");
    expect(within(menu).getByRole("menuitemradio", { name: "라디오 하나" }).getAttribute("aria-checked")).toBe("false");
    expect(within(menu).getByRole("menuitemradio", { name: "라디오 둘" }).getAttribute("aria-checked")).toBe("true");
    expect(within(menu).getByRole("group", { name: "묶음" })).toBeTruthy();
    fireEvent.keyDown(check, { key: "End" });
    expect(document.activeElement).toBe(within(menu).getByRole("menuitemradio", { name: "라디오 둘" }));
    fireEvent.click(check);
    expect(onCheck).toHaveBeenCalledWith(false);
    expect(screen.queryByRole("menu")).not.toBeNull(); // 체크 항목은 눌러도 열려 있다
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("항목을 고르면 실행하고 닫는다. 실행할 항목이 없으면 단추를 그리지 않는다", () => {
    const pick = vi.fn();
    render(<ActionMenu label="메뉴" trigger="⋯" entries={entries(pick, () => undefined)} />);
    fireEvent.click(screen.getByRole("button", { name: "메뉴" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /첫 항목/ }));
    expect(pick).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).toBeNull();
    cleanup();
    const { container } = render(<ActionMenu label="메뉴" trigger="⋯" entries={[{ kind: "heading", id: "h", label: "빈" }]} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("viewMenuEntries([보기 ▾] 항목 구성)", () => {
  it("넘긴 것만 항목이 된다. 숨긴 범주가 없으면 '숨긴 범주 포함'이 없고, 마지막 한 열은 끌 수 없다", () => {
    const e = viewMenuEntries({
      groupResponses: { checked: true, onChange: () => undefined },
      time: { mode: "time", onChange: () => undefined },
      columns: { all: ["a", "b"], selected: ["a"], labelOf: (id) => `열-${id}`, onChange: () => undefined },
      onEditTaxonomy: () => undefined,
    });
    const labels = e.map((x) => ("label" in x ? x.label : x.kind));
    expect(labels).toEqual(["응답 묶기", "시각 표시", "날짜·시각", "시각만", "경과 시각(시작 기준)", "열 구성", "열-a", "열-b", "separator", "분류 체계 편집…"]);
    expect(e.find((x) => x.id === "time-time")).toMatchObject({ kind: "radio", checked: true });
    expect(e.find((x) => x.id === "col-a")).toMatchObject({ kind: "check", checked: true, disabled: true });
    expect(e.find((x) => x.id === "col-b")).toMatchObject({ disabled: false });
  });
  it("검색 화면: 정렬 라디오가 맨 앞에 온다", () => {
    const e = viewMenuEntries({ sort: { order: "desc", onChange: () => undefined } });
    expect(e.map((x) => x.id)).toEqual(["sort", "sort-desc", "sort-asc"]);
    expect(e[1]).toMatchObject({ checked: true });
  });
});

// ---- 화면 단위: 도달 경로 표(§3)의 기능이 줄어든 자리에서 닿는다. 출처·범주·모델 이름은 임의 값이다.
const src = (id: string, enabled = true): LogSourceInfo => ({ descriptor: { id, title: `출처-${id}`, format: "fmt", reads_paths: false, default_enabled: false }, enabled, origin: "plugin" });
const session = (id: string): LogSessionSummary => ({ session: id, first_time: 1_700_000_000, last_time: 1_700_000_100, events: 3, errors: 1, thread_count: 2, models: ["m-1"], tokens: { total: 4100, input: 1, output: 2, cache_read: 3, cache_creation: 4 }, project: { id: "p-1", label: "내 프로젝트" }, cwd: "/work/p-1" });
const event = (n: number, over: Partial<LogEvent> = {}): LogEvent => ({ uid: `u${n}`, seq: n, source: "x", observed_at: n, category: `cat-${n}`, title: `이벤트 ${n}`, time: 1_700_000_000 + n, thread: "th-1", ...over });
const timeline = (): LogTimeline => ({ session: session("ses-1"), lanes: [{ id: "th-1", label: "메인 줄" }], events: [1, 2, 3, 4, 5, 6].map((n) => event(n)), total: 6 });

function mount(path: string, rest: Record<string, unknown> = {}, settings: WorkspaceSettings = {}) {
  const { clients } = createFakeClients({
    getSettingsVersioned: async () => ({ value: settings, version_hash: "s1" }),
    getLogTaxonomy: async () => ({ categories: {} }),
    getLogSchema: async () => {
      throw new ApiError(404, { code: "not_found", message: "없음" });
    },
    listLogSources: async () => [src("a")],
    ...rest,
  });
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return { clients, router };
}

describe("로그 화면: 기능이 줄어든 자리에서 닿는다(AC-1·AC-3)", () => {
  it("헤더는 [⟳][⋯] 둘뿐이고, 세션 상세 [⋯]에 지금 수집·보관본·세션 id 복사가 있다", async () => {
    mount("/logs/sessions/ses-1", { getLogTimeline: async () => timeline() });
    await screen.findByRole("slider", {}, LONG);
    const header = document.querySelector(".ac-pageheader-actions") as HTMLElement;
    expect(within(header).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual(["새로 고침", "더 보기"]);
    expect(screen.queryByRole("button", { name: /^지금 수집$/ })).toBeNull();
    fireEvent.click(within(header).getByRole("button", { name: "더 보기" }));
    const menu = await screen.findByRole("menu", { name: "더 보기" });
    const names = within(menu).getAllByRole("menuitem").map((x) => x.textContent ?? "");
    expect(names.some((x) => x.includes("지금 수집"))).toBe(true);
    expect(names.some((x) => /보관본.*HTML/.test(x))).toBe(true);
    expect(names.some((x) => /보관본.*JSON/.test(x))).toBe(true);
    expect(names.some((x) => x.includes("세션 id 복사"))).toBe(true);
  });

  it("[세션 정보]에 모델·토큰(분해)·시작·길이·에이전트 수·전체 id가 있고 I 키로도 열린다", async () => {
    mount("/logs/sessions/ses-1", { getLogTimeline: async () => timeline() });
    await screen.findByRole("slider", {}, LONG);
    fireEvent.click(screen.getByRole("button", { name: "세션 정보" }));
    const pop = await screen.findByRole("dialog", { name: "세션 정보" });
    for (const text of ["ses-1", "m-1", "4,100", "입력 1", "캐시 읽기 3", "내 프로젝트", "/work/p-1"]) expect(pop.textContent, text).toContain(text);
    fireEvent.keyDown(pop, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "세션 정보" })).toBeNull());
    fireEvent.keyDown(document.body, { key: "i" });
    await screen.findByRole("dialog", { name: "세션 정보" });
  });

  it("[재생 설정]에 속도·공백 건너뛰기가 있고 [보기]에 응답 묶기·시각 표시·열 구성·분류 체계 편집이 있다. 막대에는 속도 select가 없다", async () => {
    const { router } = mount("/logs/sessions/ses-1", { getLogTimeline: async () => timeline() });
    await screen.findByRole("slider", {}, LONG);
    expect(screen.queryByLabelText("속도")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "재생 설정" }));
    expect(screen.getByLabelText("속도")).toBeTruthy();
    expect(screen.getByLabelText("공백 건너뛰기")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("dialog", { name: "재생 설정" }), { key: "Escape" });

    fireEvent.click(screen.getByRole("button", { name: "보기" }));
    const menu = await screen.findByRole("menu", { name: "보기" });
    expect(within(menu).getByRole("menuitemcheckbox", { name: "응답 묶기" }).getAttribute("aria-checked")).toBe("true");
    expect(within(menu).queryByRole("menuitemcheckbox", { name: "숨긴 범주 포함" })).toBeNull(); // 숨긴 범주가 없으면 항목 없음
    expect(within(menu).getAllByRole("menuitemradio")).toHaveLength(3); // 날짜·시각 / 시각만 / 경과
    expect(within(menu).getByRole("group", { name: "열 구성" })).toBeTruthy();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "분류 체계 편집…" }));
    await waitFor(() => expect(router.state.location.pathname + router.state.location.hash).toBe("/settings#log-taxonomy"), LONG);
  });

  it("범주 칩은 전체 + 4개이고 나머지는 [더 보기 ▾ (+n)] 뒤에 있다. 오류만은 눌림 단추다", async () => {
    mount("/logs/sessions/ses-1", { getLogTimeline: async () => timeline() });
    const chips = await screen.findByRole("group", { name: "범주 필터" }, LONG);
    await waitFor(() => expect(within(chips).getAllByRole("button").length).toBeGreaterThan(2), LONG);
    expect(within(chips).getAllByRole("button")).toHaveLength(1 + 4 + 1);
    const more = within(chips).getByRole("button", { name: /더 보기 ▾ \(\+2\)/ });
    fireEvent.click(more);
    expect(within(chips).getAllByRole("button")).toHaveLength(1 + 6 + 1);
    expect(screen.getByRole("button", { name: /오류만/ }).getAttribute("aria-pressed")).toBe("false");
  });

  it("★ 단추 없이 [+ 필터] 메뉴 맨 아래에 즐겨찾는 필터 구역이 있다(세션 목록)", async () => {
    mount("/logs/sessions?range=all", { listLogSessions: async () => [session("ses-1")] });
    await screen.findByRole("grid", { name: "세션 목록" }, LONG);
    expect(screen.queryByRole("button", { name: "즐겨찾는 필터" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "+ 필터" }));
    const group = screen.getByRole("group", { name: "즐겨찾는 필터" });
    expect(group.textContent).toContain("저장된 필터가 없습니다");
  });

  it("검색: 헤더 [⋯]에 보관본이, [보기]에 정렬·시각·열이 있고 handoff 보기에서는 [보기]가 없다", async () => {
    mount("/logs/search?range=all", { listLogEvents: async () => ({ items: [event(1)], total: 1 }) });
    await screen.findByRole("grid", { name: "이벤트 표" }, LONG);
    fireEvent.click(screen.getByRole("button", { name: "보기" }));
    const view = await screen.findByRole("menu", { name: "보기" });
    expect(within(view).getByRole("group", { name: "정렬" })).toBeTruthy();
    expect(within(view).getByRole("group", { name: "시각 표시" })).toBeTruthy();
    expect(within(view).getByRole("group", { name: "열 구성" })).toBeTruthy();
    fireEvent.keyDown(view, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "더 보기" }));
    const menu = await screen.findByRole("menu", { name: "더 보기" });
    expect(within(menu).getAllByRole("menuitem").some((x) => /보관본.*HTML/.test(x.textContent ?? ""))).toBe(true);
    expect(screen.queryByRole("button", { name: /^보관본/ })).toBeNull();
    cleanup();
    mount("/logs/search?range=all&view=handoff", { getLogHandoffs: async () => ({ cells: [] }) });
    await screen.findByRole("tablist", { name: "검색 보기" }, LONG);
    expect(screen.queryByRole("button", { name: "보기" })).toBeNull();
  });

  it("알림 줄: 비밀 가림 불가와 프로젝트 없음이 동시에 걸리면 줄에는 하나만 보이고 '외 1건'이 붙는다", async () => {
    mount("/logs/sessions", {
      listLogSessions: async () => [session("ses-1")],
      getServerInfo: async () => ({
        server_version: "1", contracts_version: "1", plugins: [], attributes: {},
        warnings: [{ code: "logs.no_projects", severity: "warning", message: "프로젝트 없음 안내" }, { code: "logs.redaction_unavailable", severity: "warning", message: "x" }],
      }),
    });
    const bar = await screen.findByTestId("logs-noticebar", {}, LONG);
    expect(bar.textContent).toContain("비밀 가림 규칙을 쓸 수 없어");
    expect(bar.textContent).not.toContain("프로젝트 없음 안내");
    expect(within(bar).getByRole("button", { name: /외 1건/ })).toBeTruthy();
  });

  it("알림이 없으면 알림 줄 자체가 없다", async () => {
    mount("/logs/sessions", { listLogSessions: async () => [session("ses-1")] });
    await screen.findByRole("grid", { name: "세션 목록" }, LONG);
    expect(screen.queryByTestId("logs-noticebar")).toBeNull();
  });
});
