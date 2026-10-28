import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { UsageReport, UsageSourceInfo, WorkspaceSettings } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";
import { createFakeClients } from "../../testing/fakes";
import { resolveIndicatorSettings } from "./indicatorSettings";

beforeAll(preloadScreens, 120_000);
afterEach(cleanup);

const now = Math.floor(Date.now() / 1000);
// 창·출처 id·tone은 임의 값이다. 앱은 이 이름들을 모른다.
const sources: UsageSourceInfo[] = [{ descriptor: { id: "src-a", title: "출처 에이", trust: "official" }, enabled: true }];
const report: UsageReport = {
  generated_at: now,
  windows: [
    { source: "src-a", window: "win-1", used_ratio: 0.63, resets_at: now + 2 * 3600 + 14 * 60, observed_at: now - 30 },
    { source: "src-a", window: "win-2", status: "weird", observed_at: now - 30 },
    { source: "src-a", window: "win-3", used_ratio: 0.1, observed_at: now - 30 },
  ],
  rollups: [],
};

/** 사이드바를 펼친 상태(저장된 값). 테스트 뷰포트는 좁아 기본이 접힘(레일)이다. */
const expandedStorage = (collapsed = "0") => createSafeStorage({ getItem: (k: string) => (k === "ac.sidebar.collapsed" ? collapsed : null), setItem: () => {}, removeItem: () => {} } as unknown as Storage);

function mount(settings: WorkspaceSettings = {}, overrides: Record<string, unknown> = {}, path = "/chat", onBackgroundError?: (e: unknown) => void, sidebar = "0") {
  const { clients, rest } = createFakeClients({
    getUsage: vi.fn(async () => report),
    listUsageSources: vi.fn(async () => sources),
    getSettingsVersioned: vi.fn(async () => ({ value: settings, version_hash: "s1" })),
    ...overrides,
  });
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: [path] });
  const queryClient = createAppQueryClient({ retry: false, ...(onBackgroundError ? { onBackgroundError } : {}) });
  render(<AppRoot createClients={async () => clients} router={router} storage={expandedStorage(sidebar)} queryClient={queryClient} />);
  return { rest, router, queryClient };
}

const indicator = () => document.querySelector(".usage-ind");
const withIndicator = (over: Record<string, unknown>): WorkspaceSettings => ({ ui: { usage_indicator: over } } as WorkspaceSettings);

describe("사용량 표시기: 기본 설정", () => {
  it("스키마 기본값에서 읽은 설정이 적용된다(코드에 복사한 값이 없다)", () => {
    expect(resolveIndicatorSettings(undefined)).toMatchObject({ enabled: true, placement: "sidebar-bottom", windows: [], max_items: 2, fields: ["label", "value", "gauge"], value_mode: "used", color_rules: [{ at: 0, tone: "success" }, { at: 0.7, tone: "warning" }, { at: 0.9, tone: "danger" }], hide_when_empty: false, also_in_title: false });
    expect(resolveIndicatorSettings({ max_items: 4 }).max_items).toBe(4);
  });

  it("사이드바 푸터에 앞 2개 창이 보이고 주 메뉴 nav 밖이며 탭 정지는 링크 1개다", async () => {
    mount();
    const link = await screen.findByRole("link", { name: /^사용량: win-1 사용 63%, 초기화까지 2시간 1\d분\. win-3 사용 10%\./ });
    const nav = screen.getByRole("navigation", { name: "주 메뉴" });
    expect(nav.contains(link)).toBe(false);
    expect(nav.textContent).not.toMatch(/63%/);
    expect(link.getAttribute("href")).toBe("/usage");
    // 상태만 주는 창(win-2)은 사이드바에 없고, 값이 있는 창만 앞에서 max_items(기본 2)개
    expect(link.getAttribute("aria-label")).not.toMatch(/win-2|weird|사용률 정보 없음/);
    expect(link.getAttribute("aria-label")).toMatch(/눌러서 사용량 화면 열기$/);
    expect(indicator()!.closest(".ac-sidebar-footer")).not.toBeNull();
    expect(indicator()!.querySelectorAll("a, button, [tabindex]").length).toBe(1);
    expect(indicator()!.querySelector(".ac-gauge")!.closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it("클릭하면 사용량 화면으로 이동한다(경로는 라우트 설정에서)", async () => {
    const { router } = mount();
    fireEvent.click(await screen.findByRole("link", { name: /^사용량:/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/usage"));
  });

  it("사용량 화면에서는 aria-current이고 보고 요청은 표시기(창만)와 화면(전체) 각 한 번이고 출처 요청은 합쳐진다", async () => {
    const { rest } = mount({}, {}, "/usage");
    const link = await screen.findByRole("link", { name: /^사용량:/ });
    expect(link.getAttribute("aria-current")).toBe("page");
    await screen.findByRole("heading", { name: "사용량", level: 1 });
    // 표시기는 창 부분만(`parts=windows`), 화면은 전체 보고를 따로 읽는다(응답 모양이 달라 캐시 키를 나눴다). 각각 한 번.
    expect(rest.getUsage).toHaveBeenCalledTimes(2);
    expect(rest.getUsage).toHaveBeenCalledWith(["windows"]);
    expect(rest.getUsage).toHaveBeenCalledWith();
    expect(rest.listUsageSources).toHaveBeenCalledTimes(1);
  });

  it("사이드바가 접히면 레일 모양(숫자 + 막대만, 이름은 aria-label·툴팁)이고 aria-label은 그대로다", async () => {
    mount({}, {}, "/chat", undefined, "1");
    const link = await screen.findByRole("link", { name: /^사용량: win-1 사용 63%/ });
    expect(indicator()!.getAttribute("data-layout")).toBe("rail");
    expect(indicator()!.querySelector(".usage-ind-rail-name")).toBeNull();
    expect(indicator()!.querySelector(".usage-ind-rail-value")!.textContent).toBe("63%");
    expect(link.getAttribute("href")).toBe("/usage");
  });

  it("호버하지 않아도 값은 aria-label에 있고, 포커스하면 비대화형 요약 팝오버가 열리며 Esc로 닫힌다", async () => {
    mount();
    const link = await screen.findByRole("link", { name: /^사용량:/ });
    fireEvent.focus(link);
    const pop = await screen.findByRole("group", { name: "사용량" });
    expect(within(pop).getByText("63% 사용됨")).toBeTruthy();
    expect(within(pop).getByText("win-3")).toBeTruthy(); // 표시 대상이 아니어도 관측된 창은 팝오버에 있다
    expect(link.getAttribute("aria-describedby")).toBe(pop.id);
    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("group", { name: "사용량" })).toBeNull());
  });

  it("Alt+U로 요약을 낭독 영역에 알린다", async () => {
    mount();
    await screen.findByRole("link", { name: /^사용량:/ });
    fireEvent.keyDown(document.body, { key: "u", altKey: true });
    await waitFor(() => expect(indicator()!.querySelector('[aria-live="polite"]')!.textContent).toMatch(/win-1 사용 63%/));
  });
});

describe("사용량 표시기: 미니 모양(5.2R.57)", () => {
  const miniReport = (windows: UsageReport["windows"]): Record<string, unknown> => ({ getUsage: vi.fn(async () => ({ generated_at: now, windows, rollups: [] })) });
  const rows = () => Array.from(document.querySelectorAll(".usage-ind-simple .usage-ind-head"));

  it("기본 색 규칙은 계약 데이터에서 온다: 63%는 success 톤, 글리프 없음, 퍼센트 글자색은 톤이 아니다", async () => {
    mount();
    await screen.findByRole("link", { name: /^사용량:/ });
    const item = document.querySelector<HTMLElement>('.usage-ind-item[data-tone="success"]')!;
    expect(item).not.toBeNull();
    expect(item.style.getPropertyValue("--ac-gauge-fill")).toBe("var(--ac-success)");
    expect(item.querySelector(".usage-ind-value")!.textContent).toBe("63% 사용됨");
    expect(item.querySelector(".usage-ind-tone")).toBeNull();
  });

  it("경고는 ▲, 위험은 ✕ 글리프가 퍼센트 뒤에 붙는다", async () => {
    mount({}, miniReport([
      { source: "src-a", window: "win-1", used_ratio: 0.75, observed_at: now - 30 },
      { source: "src-a", window: "win-2", used_ratio: 0.93, observed_at: now - 30 },
    ]));
    await screen.findByRole("link", { name: /^사용량:/ });
    const [a, b] = rows().map((r) => r.querySelector(".usage-ind-value")!.textContent);
    expect(a).toBe("75% 사용됨▲");
    expect(b).toBe("93% 사용됨✕");
  });

  it("상태·토큰만 주는 창은 사이드바에 그리지 않고 '사용량 정보 없음' 한 줄만 보인다(사용자 요청 10/28)", async () => {
    mount({}, miniReport([
      { source: "src-a", window: "win-1", status: "idle", observed_at: now - 30 },
      { source: "src-a", window: "win-2", used_tokens: 1_100_000_000, observed_at: now - 30 },
    ]));
    await screen.findByRole("link", { name: /^사용량:/ });
    expect(indicator()!.textContent).toBe("사용량 정보 없음");
    expect(indicator()!.textContent).not.toMatch(/idle|1\.1G|유휴|토큰/i);
    expect(indicator()!.querySelector(".ac-gauge")).toBeNull();
  });

  it("사이드바 항목은 제목·'N% 사용됨'·막대·초기화 시각만 있다(신뢰·관측 시각·상태 없음)", async () => {
    mount();
    await screen.findByRole("link", { name: /^사용량:/ });
    const item = document.querySelector<HTMLElement>(".usage-ind-simple")!;
    expect(Array.from(item.children).map((c) => c.className.split(" ")[0])).toEqual(["usage-ind-head", "usage-ind-bar", "usage-ind-sub"]);
    expect(item.querySelector(".usage-ind-label")!.textContent).toBe("win-1");
    expect(item.querySelector(".usage-ind-sub")!.textContent).toMatch(/에 초기화$/);
    expect(item.textContent).not.toMatch(/◆|관측|⚠/);
    expect(document.querySelectorAll(".usage-ind-simple").length).toBe(2); // win-2(상태)는 건너뛰고 win-1·win-3
  });

  it("추정 출처의 값은 툴팁에 추정(로컬 로그)을 적는다(사이드바 글자에는 ~를 붙이지 않는다)", async () => {
    const est: UsageSourceInfo[] = [{ descriptor: { id: "src-a", title: "로컬", trust: "estimated" }, enabled: true }];
    mount({}, { ...miniReport([{ source: "src-a", window: "win-1", used_ratio: 0.42, observed_at: now - 30 }]), listUsageSources: vi.fn(async () => est) });
    await screen.findByRole("link", { name: /^사용량:/ });
    await waitFor(() => expect(rows()[0]!.querySelector(".usage-ind-value")!.textContent).toBe("42% 사용됨"));
    expect(document.querySelector(".usage-ind-item")!.getAttribute("title")).toMatch(/추정\(로컬 로그\)/);
  });

  it("모든 창이 값이 없고 구독 연결 출처가 있으면 한 줄 안내가 #setup으로 이어진다. 없으면 안내가 없다", async () => {
    const needs: UsageSourceInfo[] = [{ descriptor: { id: "src-a", title: "공식", trust: "official", needs_setup: true }, enabled: true }];
    mount({}, { ...miniReport([{ source: "src-a", window: "win-1", status: "idle", observed_at: now - 30 }]), listUsageSources: vi.fn(async () => needs) });
    const link = await screen.findByRole("link", { name: /^사용량:/ });
    await waitFor(() => expect(link.getAttribute("href")).toBe("/usage#setup"));
    expect(indicator()!.textContent).toMatch(/사용률 미연결/);
    expect(indicator()!.textContent).not.toMatch(/연결 방법|›/); // 줄 전체가 링크다(따로 강조된 글자 없음)
    expect(link.getAttribute("aria-label")).toMatch(/상태 줄을 연결/);
    expect(document.querySelector(".ac-gauge")).toBeNull();
  });

  it("hide_when_empty면 미연결 안내도 그리지 않는다", async () => {
    const needs: UsageSourceInfo[] = [{ descriptor: { id: "src-a", title: "공식", trust: "official", needs_setup: true }, enabled: true }];
    mount(withIndicator({ hide_when_empty: true }), { ...miniReport([{ source: "src-a", window: "win-1", status: "idle", observed_at: now - 30 }]), listUsageSources: vi.fn(async () => needs) });
    // 보일 사용률이 없으니 표시기 자체를 그리지 않는다(상태만 주는 창은 값으로 치지 않는다)
    await screen.findByRole("navigation", { name: "주 메뉴" });
    await act(async () => {});
    expect(indicator()).toBeNull();
  });
});

describe("사용량 표시기: 컨텍스트 메뉴", () => {
  const openByContext = async () => {
    const link = await screen.findByRole("link", { name: /^사용량:/ });
    fireEvent.contextMenu(link, { clientX: 20, clientY: 30 });
    return { link, menu: await screen.findByRole("menu", { name: "사용량 표시기 메뉴" }) };
  };

  it("우클릭으로 열리고 네 항목이 있으며 첫 항목에 포커스가 간다", async () => {
    mount();
    const { menu } = await openByContext();
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["사용량 열기", "지금 새로 고침", "표시 설정…", "숨기기"]);
    expect(document.activeElement).toBe(within(menu).getByRole("menuitem", { name: "사용량 열기" }));
  });

  it("Shift+F10과 ContextMenu 키로도 열리고, 방향키로 이동하며 Esc로 닫고 링크로 돌아온다", async () => {
    mount();
    const link = await screen.findByRole("link", { name: /^사용량:/ });
    link.focus();
    fireEvent.keyDown(link, { key: "F10", shiftKey: true });
    const menu = await screen.findByRole("menu", { name: "사용량 표시기 메뉴" });
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(within(menu).getByRole("menuitem", { name: "지금 새로 고침" }));
    fireEvent.keyDown(menu, { key: "End" });
    expect(document.activeElement).toBe(within(menu).getByRole("menuitem", { name: "숨기기" }));
    fireEvent.keyDown(menu, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(document.activeElement).toBe(link);
    fireEvent.keyDown(link, { key: "ContextMenu" });
    expect(await screen.findByRole("menu")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Tab" });
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("[사용량 열기]와 [표시 설정…]은 라우트 설정의 경로로 이동한다", async () => {
    const { router } = mount();
    let { menu } = await openByContext();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "표시 설정…" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings"));
    expect(router.state.location.hash).toBe("#usage");
    ({ menu } = await openByContext());
    fireEvent.click(within(menu).getByRole("menuitem", { name: "사용량 열기" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/usage"));
  });

  it("[지금 새로 고침]은 직전 조회가 5초 안이면 무시하고 안내, 지나면 다시 조회하며 연타는 한 번만", async () => {
    const { rest } = mount();
    await screen.findByRole("link", { name: /^사용량:/ });
    const calls = () => (rest.getUsage as unknown as { mock: { calls: unknown[] } }).mock.calls.length;
    const before = calls();
    let { menu } = await openByContext();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "지금 새로 고침" }));
    expect(indicator()!.querySelector('[aria-live="polite"]')!.textContent).toBe("방금 새로 고쳤습니다. 잠시 뒤에 다시 시도하세요");
    expect(calls()).toBe(before);
    const real = Date.now();
    const spy = vi.spyOn(Date, "now").mockReturnValue(real + 6_000);
    try {
      ({ menu } = await openByContext());
      fireEvent.click(within(menu).getByRole("menuitem", { name: "지금 새로 고침" }));
      await waitFor(() => expect(calls()).toBe(before + 1));
      ({ menu } = await openByContext());
      fireEvent.click(within(menu).getByRole("menuitem", { name: "지금 새로 고침" }));
      expect(indicator()!.querySelector('[aria-live="polite"]')!.textContent).toBe("방금 새로 고쳤습니다. 잠시 뒤에 다시 시도하세요");
      expect(calls()).toBe(before + 1);
    } finally {
      spy.mockRestore();
    }
  });

  it("[숨기기]는 설정 ui.usage_indicator.enabled=false를 If-Match로 저장하고 표시기가 사라진다", async () => {
    const { rest } = mount(withIndicator({ max_items: 3 }));
    const { menu } = await openByContext();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "숨기기" }));
    await waitFor(() => expect(rest.putSettingsVersioned).toHaveBeenCalledWith({ ui: { usage_indicator: { max_items: 3, enabled: false } } }, "s1"));
    await waitFor(() => expect(indicator()).toBeNull());
  });
});

describe("사용량 표시기: 플로팅 칩 +N", () => {
  const withMatchMedia = (matches: boolean) => {
    const orig = window.matchMedia;
    window.matchMedia = ((q: string) => ({ matches: q.includes("639") ? matches : false, media: q, addEventListener: () => {}, removeEventListener: () => {} })) as unknown as typeof window.matchMedia;
    return () => {
      window.matchMedia = orig;
    };
  };

  it("640px 이상이면 설정한 항목 수를 그대로 보인다", async () => {
    const restore = withMatchMedia(false);
    try {
      mount(withIndicator({ placement: "float-bottom-right", max_items: 3 }));
      await screen.findByRole("link", { name: /^사용량:/ });
      expect(indicator()!.querySelectorAll(".usage-ind-chip-item").length).toBe(3);
      expect(indicator()!.querySelector(".usage-ind-chip-more")).toBeNull();
    } finally {
      restore();
    }
  });

  it("640px 미만이면 항목 1개와 +N(툴팁에 나머지)이고 aria-label에는 전부 있다", async () => {
    const restore = withMatchMedia(true);
    try {
      mount(withIndicator({ placement: "float-bottom-right", max_items: 3 }));
      const link = await screen.findByRole("link", { name: /^사용량:/ });
      await waitFor(() => expect(indicator()!.querySelectorAll(".usage-ind-chip-item").length).toBe(1));
      const more = indicator()!.querySelector(".usage-ind-chip-more")!;
      expect(more.textContent).toBe("+2");
      expect(more.getAttribute("title")).toMatch(/win-2/);
      expect(more.getAttribute("title")).toMatch(/win-3/);
      expect(link.getAttribute("aria-label")).toMatch(/win-3/);
    } finally {
      restore();
    }
  });
});

describe("사용량 표시기: 설정", () => {
  it("남은 양/사용한 양, 항목 선택, 창 지정", async () => {
    mount(withIndicator({ value_mode: "used", windows: ["win-3", "win-x"], fields: ["label", "value"] }));
    const link = await screen.findByRole("link", { name: /^사용량:/ });
    expect(link.getAttribute("aria-label")).toMatch(/^사용량: win-3 사용 10%\. 눌러서/);
    // 사이드바 항목은 `fields` 설정과 상관없이 제목·값·막대·초기화 시각 고정(fields는 칩 모양에만 적용)
    expect(indicator()!.querySelector(".ac-gauge")).not.toBeNull();
    expect(indicator()!.textContent).toContain("10% 사용됨");
    expect(indicator()!.textContent).not.toContain("win-x"); // 관측 없는 창은 사이드바에 그리지 않는다
  });

  it("색 규칙이 적용되면 아이콘과 문장을 함께 쓴다(색 단독 아님)", async () => {
    mount(withIndicator({ value_mode: "used", color_rules: [{ at: 0.5, tone: "warning" }, { at: 0.95, tone: "danger" }] }));
    const link = await screen.findByRole("link", { name: /^사용량:/ });
    expect(link.getAttribute("aria-label")).toMatch(/규칙 적용: 경고\(사용률 50% 이상\)/);
    expect(indicator()!.querySelector(".usage-ind-tone")!.textContent).toBe("▲");
    expect(indicator()!.querySelectorAll(".usage-ind-tone").length).toBe(1);
  });

  it("모르는 tone/field/placement는 오류 없이 대체된다", async () => {
    mount(withIndicator({ placement: "nowhere", fields: ["label", "wat", "value"], color_rules: [{ at: 0.1, tone: "no-such-tone" }] }));
    await screen.findByRole("link", { name: /^사용량:/ });
    expect(indicator()!.closest(".ac-sidebar-footer")).not.toBeNull();
    expect(indicator()!.querySelector(".usage-ind-tone")).toBeNull();
  });

  it("sidebar-top 배치는 로고 줄 아래(헤더), float 배치는 사이드바 밖 본문 쪽에 한 곳만 보인다", async () => {
    const top = mount(withIndicator({ placement: "sidebar-top" }));
    await screen.findByRole("link", { name: /^사용량:/ });
    expect(document.querySelectorAll(".usage-ind").length).toBe(1);
    expect(indicator()!.closest(".ac-sidebar-header")).not.toBeNull();
    cleanup();
    void top;
    mount(withIndicator({ placement: "float-bottom-left" }));
    await screen.findByRole("link", { name: /^사용량:/ });
    expect(document.querySelectorAll(".usage-ind").length).toBe(1);
    expect(indicator()!.closest(".ac-sidebar")).toBeNull();
    expect(indicator()!.getAttribute("data-corner")).toBe("bottom-left");
  });

  it("hide_when_empty면 관측이 없을 때 렌더하지 않고, 기본이면 '사용량 정보 없음'을 보인다", async () => {
    const empty = { getUsage: vi.fn(async () => ({ windows: [], rollups: [], generated_at: now })) };
    mount(withIndicator({ hide_when_empty: true }), empty);
    await screen.findByRole("navigation", { name: "주 메뉴" });
    await waitFor(() => expect((empty.getUsage as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0));
    await act(async () => {});
    expect(indicator()).toBeNull();
    cleanup();
    mount({}, empty);
    expect((await screen.findByRole("link", { name: /^사용량:/ })).textContent).toContain("사용량 정보 없음");
  });

  it("also_in_title이면 제목 끝에 첫 항목이 붙고, 끄면 이전 제목 그대로", async () => {
    mount(withIndicator({ also_in_title: true }));
    await waitFor(() => expect(document.title).toMatch(/ · Agent Console · win-1 63%$/));
    cleanup();
    mount();
    await screen.findByRole("link", { name: /^사용량:/ });
    expect(document.title).not.toMatch(/win-1/);
  });
});

describe("사용량 표시기: 끄면 이전과 같다", () => {
  it("enabled=false: DOM·사용량 요청·단축키·제목 변화가 없다", async () => {
    const { rest } = mount(withIndicator({ enabled: false, also_in_title: true }));
    await screen.findByRole("navigation", { name: "주 메뉴" });
    await waitFor(() => expect(rest.getSettingsVersioned).toHaveBeenCalled());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(indicator()).toBeNull();
    expect(document.querySelector(".ac-sidebar-footer [aria-live], .usage-ind-link")).toBeNull();
    expect(rest.getUsage).not.toHaveBeenCalled();
    expect(rest.listUsageSources).not.toHaveBeenCalled();
    fireEvent.keyDown(document.body, { key: "u", altKey: true });
    expect(document.querySelector(".usage-ind")).toBeNull();
    expect(document.title).not.toMatch(/win-1|사용량/);
  });

  it("설정을 읽기 전에는 마운트하지 않아 요청도 없다", async () => {
    const never = { getSettingsVersioned: vi.fn(() => new Promise(() => {})) };
    const { rest } = mount({}, never);
    await screen.findByRole("navigation", { name: "주 메뉴" });
    expect(indicator()).toBeNull();
    expect(rest.getUsage).not.toHaveBeenCalled();
  });
});

describe("사용량 표시기: 서버 실패와 토스트", () => {
  it("사용량 화면이 아닌 곳에서 갱신이 반복 실패해도 오류 알림이 0건이고 !만 보인다", async () => {
    let fail = false;
    const getUsage = vi.fn(async () => {
      if (fail) throw new Error("서버 끊김");
      return report;
    });
    const onBackgroundError = vi.fn();
    const { queryClient } = mount({}, { getUsage }, "/chat", onBackgroundError);
    await screen.findByRole("link", { name: /^사용량:/ });
    fail = true;
    for (let i = 0; i < 3; i += 1) await act(async () => void (await queryClient.invalidateQueries({ queryKey: ["usage"] })));
    expect(getUsage.mock.calls.length).toBeGreaterThan(3);
    await waitFor(() => expect(indicator()!.getAttribute("data-error")).toBe("true"));
    expect(onBackgroundError).not.toHaveBeenCalled();
    expect(indicator()!.querySelector(".usage-ind-err")).not.toBeNull();
  });

  it("사용량 화면이 같은 키를 보고 있으면 기존 토스트 동작이 그대로다", async () => {
    let fail = false;
    const getUsage = vi.fn(async () => {
      if (fail) throw new Error("서버 끊김");
      return report;
    });
    const onBackgroundError = vi.fn();
    const { queryClient } = mount({}, { getUsage }, "/usage", onBackgroundError);
    await screen.findByRole("heading", { name: "사용량", level: 1 });
    await screen.findByRole("link", { name: /^사용량:/ });
    fail = true;
    await act(async () => void (await queryClient.invalidateQueries({ queryKey: ["usage"] })));
    await waitFor(() => expect(onBackgroundError).toHaveBeenCalled());
  });

  it("데이터가 한 번도 없으면 한 줄 오류만 보인다", async () => {
    const getUsage = vi.fn(async () => {
      throw new Error("x");
    });
    const onBackgroundError = vi.fn();
    mount({}, { getUsage }, "/chat", onBackgroundError);
    const link = await screen.findByRole("link", { name: /사용량을 불러오지 못했습니다/ });
    expect(link.textContent).toContain("사용량을 불러오지 못했습니다");
    expect(onBackgroundError).not.toHaveBeenCalled();
  });
});

describe("IndicatorMenu 위치: 실측 기반", () => {
  it("크기를 받아 뷰포트 안으로 맞춘다(매직 넘버 없음)", async () => {
    const { clampToViewport } = await import("./IndicatorMenu");
    const vp = { width: 1000, height: 800 };
    expect(clampToViewport({ x: 990, y: 790 }, { width: 180, height: 120 }, vp, 8)).toEqual({ x: 812, y: 672 });
    expect(clampToViewport({ x: 10, y: 10 }, { width: 180, height: 120 }, vp, 8)).toEqual({ x: 10, y: 10 });
    expect(clampToViewport({ x: -5, y: -5 }, { width: 2000, height: 2000 }, vp, 8)).toEqual({ x: 8, y: 8 });
  });
});
