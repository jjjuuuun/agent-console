import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { beforeAll, afterEach, describe, expect, it } from "vitest";
import type { UsageReport, UsageSourceInfo, WorkspaceSettings } from "@agent-console/contracts";
import { AppRoot } from "../../app/AppRoot";
import { createAppQueryClient } from "../../app/queries";
import { createSafeStorage } from "../../app/storage";
import { buildAppRoutes, preloadScreens } from "../../shell/routes";

// 화면은 처음 열 때 내려받는다(lazyScreen). 느린 파일시스템에서 첫 이동이 제한 시간을 넘지 않게 미리 불러온다.
beforeAll(preloadScreens, 120_000);
import { createFakeClients } from "../../testing/fakes";

afterEach(cleanup);

const now = Math.floor(Date.now() / 1000);
// 출처 id·창 id는 임의 값이다. 앱은 이 이름들을 모른다.
const sources: UsageSourceInfo[] = [
  { descriptor: { id: "src-off", title: "공식 출처", trust: "official", description: "공식 출처 설명" }, enabled: true, last_observed_at: now - 120 },
  { descriptor: { id: "src-obs", title: "관측 출처", trust: "observed", setup_help: "설정 방법 본문 `echo hi`", docs_url: "https://example.test/doc" }, enabled: true },
  { descriptor: { id: "src-new", title: "새 등급 출처", trust: "brand-new" }, enabled: false },
  { descriptor: { id: "src-silent", title: "조용한 출처", trust: "official", setup_help: "한 줄 설정 `echo hi`" }, enabled: true },
];

function report(extra: Partial<UsageReport> = {}): UsageReport {
  return {
    generated_at: now,
    windows: [
      { source: "src-off", window: "win-1", used_ratio: 0.63, status: "allowed", resets_at: now + 2 * 3600 + 14 * 60, observed_at: now - 720 },
      { source: "src-obs", window: "win-1", used_ratio: 0.9, observed_at: now - 30 },
      { source: "src-obs", window: "win-2", status: "allowed_warning", resets_at: now + 3 * 86400, observed_at: now - 2600 },
      { source: "src-obs", window: "win-3", used_tokens: 1234, resets_at: now - 60, observed_at: now - 10 },
      { source: "src-new", window: "win-4", status: "weird-status", observed_at: now - 5 },
    ],
    rollups: [
      { agent_id: "a1", graph_id: "g1", model: "m-x", day: new Date().toISOString().slice(0, 10), usage: { input_tokens: 90, output_tokens: 30, total_tokens: 120 } },
      { agent_id: "a2", graph_id: "g1", model: "m-x", day: new Date().toISOString().slice(0, 10), usage: { total_tokens: 54 }, precision: "총 토큰만" },
    ],
    ...extra,
  };
}

function mount(overrides: Record<string, unknown> = {}, settings: WorkspaceSettings = {}) {
  const { clients } = createFakeClients({
    getUsage: async () => report(),
    listUsageSources: async () => sources,
    getSettingsVersioned: async () => ({ value: settings, version_hash: "s1" }),
    listAgents: async () => [{ id: "a1", name: "에이전트 하나" }, { id: "a2", name: "에이전트 둘" }],
    ...overrides,
  });
  const router = createMemoryRouter(buildAppRoutes({ platform: "other" }), { initialEntries: ["/usage"] });
  render(<AppRoot createClients={async () => clients} router={router} storage={createSafeStorage(null)} queryClient={createAppQueryClient({ retry: false })} />);
  return clients;
}

async function card(name: string): Promise<HTMLElement> {
  const cards = await screen.findAllByRole("group", { name: new RegExp(`(^|\\s)${name},`) });
  return cards[0]!;
}

describe("사용량 화면: 창 카드", () => {
  it("창 이름은 '출처 제목 + 창 id' 폴백이고 값은 '사용' 기준이며, 대표값은 가장 최근의 공식 출처이며 다른 출처는 접혀 있다", async () => {
    mount();
    const c = await card("win-1");
    expect(c.getAttribute("aria-label")).toMatch(/^공식 출처 win-1, 63% 사용,/);
    expect(within(c).getByText("63% 사용")).toBeTruthy();
    expect(c.textContent).not.toMatch(/남음/);
    expect(within(c).getByRole("meter").getAttribute("aria-valuenow")).toBe("0.63");
    expect(within(c).getByText("공식")).toBeTruthy();
    expect(within(c).getByText(/초기화까지 2시간 1\d분/)).toBeTruthy();
    expect(within(c).getByText("대표값: 가장 최근 공식 출처")).toBeTruthy();
    expect(within(c).queryByText("90% 사용")).toBeNull();
    fireEvent.click(within(c).getByRole("button", { name: /다른 출처 \(1\)/ }));
    expect(within(c).getByText("90% 사용")).toBeTruthy();
  });

  it("상태만 주는 창은 퍼센트를 그리지 않고, 모르는 상태는 원문으로 보인다", async () => {
    mount();
    const c = await card("win-2");
    expect(within(c).getByText("허용 (경고)")).toBeTruthy();
    expect(within(c).getByText(/사용률 정보 없음/)).toBeTruthy();
    expect(within(c).queryByRole("meter")).toBeNull();
    expect(c.textContent).not.toMatch(/\d+%/);
    const odd = await card("win-4");
    expect(within(odd).getByText("weird-status")).toBeTruthy();
    expect(within(odd).getByText("새 등급 출처")).toBeTruthy();
    expect(within(odd).getByText("brand-new")).toBeTruthy();
  });

  it("토큰 수만 주는 창은 한도 정보 없음, 게이지 없음 · 초기화 시각이 지났으면 사실로 표시", async () => {
    mount();
    const c = await card("win-3");
    expect(within(c).getByText("1.2k 토큰 사용")).toBeTruthy(); // 컴팩트 표기(정확한 수는 툴팁)
    expect(within(c).getByText("한도 정보 없음")).toBeTruthy();
    expect(within(c).queryByRole("meter")).toBeNull();
    expect(within(c).getByText(/초기화 시각이 지났습니다/)).toBeTruthy();
  });

  it("stale_after_seconds가 null이면 오래된 관측 칩이 없고, 숫자로 정하면 그보다 오래된 카드에만 붙는다", async () => {
    mount();
    await card("win-2");
    expect(screen.queryByText(/오래된 관측/)).toBeNull();
    cleanup();
    mount({}, { usage: { stale_after_seconds: 600 } });
    const old = await card("win-2");
    expect(within(old).getByText(/오래된 관측/)).toBeTruthy();
    const fresh = await card("win-4");
    expect(within(fresh).queryByText(/오래된 관측/)).toBeNull();
  });

  it("창 표시 이름은 설정 window_labels, 대표값 순서는 primary_source_order를 따른다", async () => {
    mount({}, { usage: { window_labels: { "win-1": "5시간 창" }, primary_source_order: ["src-obs", "src-off"] } });
    const c = await card("5시간 창");
    expect(within(c).getByText("90% 사용")).toBeTruthy();
    expect(within(c).getByText("대표값: 설정한 출처 순서")).toBeTruthy();
  });

  it("카드가 하나도 없으면 빈 상태 안내(출처 설명 포함)", async () => {
    mount({ getUsage: async () => report({ windows: [] }) });
    expect(await screen.findByText("아직 값이 없습니다")).toBeTruthy();
    expect(screen.getAllByText(/공식 출처 설명/).length).toBeGreaterThan(1);
  });

  it("출처가 준 창 이름(windows[])은 폴백보다 앞서고, 설정 window_labels가 가장 앞선다", async () => {
    const named = sources.map((x) => (x.descriptor.id === "src-off" ? { ...x, descriptor: { ...x.descriptor, windows: [{ id: "win-1", title: "5시간 창(출처)" }] } } : x));
    mount({ listUsageSources: async () => named });
    expect(await card("5시간 창\\(출처\\)")).toBeTruthy();
  });
});

describe("사용량 화면: 집계와 출처", () => {
  it("서브에이전트처럼 총 토큰만 오는 행에는 칩이 붙고 입력/출력은 –", async () => {
    mount();
    const list = await screen.findByRole("list", { name: "토큰 집계 막대" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows[0]!.textContent).toContain("에이전트 하나");
    expect(rows[0]!.textContent).toContain("입력 90 · 출력 30");
    expect(rows[1]!.textContent).toContain("총 토큰만");
    fireEvent.click(screen.getByRole("button", { name: "표로 보기" }));
    expect(within(screen.getByRole("table", { name: "토큰 집계 표" })).getAllByRole("row")).toHaveLength(3);
  });

  it("출처 패널: 디스크립터의 안내와 문서 링크를 그대로 보이고, 관측이 없는 출처는 안내가 펼쳐져 있다", async () => {
    mount();
    expect(await screen.findByText("공식 출처 설명")).toBeTruthy();
    // 어느 출처가 관측됐는지는 보고서에서 오므로, 보고서가 온 뒤에 접힘 상태를 본다.
    await card("win-1");
    // 관측이 없는 출처만 설정 방법이 펼쳐져 있고, 관측이 있는 출처는 접혀 있다.
    expect(screen.getByText(/이 앱은 사용자 전역 설정을 수정하지 않습니다/)).toBeTruthy();
    expect(screen.getByText("echo hi")).toBeTruthy();
    expect(screen.queryByText("설정 방법 본문")).toBeNull();
    expect(screen.getByRole("link", { name: "문서 보기" }).getAttribute("href")).toBe("https://example.test/doc");
    expect(screen.getAllByRole("link", { name: "설정에서 바꾸기" }).length).toBe(4);
  });
});

describe("사용량 화면: 단축키 도움말", () => {
  it("`?` 도움말에 새로 고침 단축키가 나온다", async () => {
    mount();
    await card("win-1");
    fireEvent.keyDown(document.body, { key: "?" });
    expect(await screen.findByText("사용량 새로 고침")).toBeTruthy();
  });
});

function setupSource(extra: Partial<UsageSourceInfo> = {}): UsageSourceInfo {
  return {
    descriptor: {
      id: "src-setup",
      title: "연결 출처",
      trust: "official",
      description: "상태 줄을 연결하면 보입니다",
      needs_setup: true,
      setup_help: "직접 붙여 넣으세요",
      setup_snippets: [
        { id: "a", title: "아직 없어요", shell: "", language: "json", text: '{"cmd":"/abs/agent-console statusline"}' },
        { id: "b-bash", title: "이미 써요", shell: "bash", language: "bash", text: "bash-snippet /abs/agent-console" },
        { id: "b-ps", title: "이미 써요", shell: "powershell", language: "powershell", text: "ps-snippet C:\\abs\\agent-console" },
      ],
    },
    enabled: true,
    ...extra,
  };
}

describe("사용량 화면: 빈 상태와 연결 안내", () => {
  const emptyReport = () => report({ windows: [] });
  const devSource: UsageSourceInfo = { descriptor: { id: "src-dev", title: "시험 출처", trust: "observed", test_only: true }, enabled: true };

  it("값이 없으면 자동으로 안내가 펼쳐지고 빈 상태에 출처별 한 줄과 [연결 방법]이 있다", async () => {
    mount({ getUsage: async () => emptyReport(), listUsageSources: async () => [sources[0]!, setupSource(), devSource] });
    expect(await screen.findByText("아직 값이 없습니다")).toBeTruthy();
    const guide = await screen.findByRole("region", { name: "상태 줄 연결 안내" });
    expect(guide.querySelector("details")!.hasAttribute("open")).toBe(true);
    expect(within(guide).getByText("직접 붙여 넣으세요")).toBeTruthy();
    expect(within(guide).getByText(/\/abs\/agent-console statusline/)).toBeTruthy();
    // [연결 방법] 진입점은 안내 패널 헤더 하나뿐이다(빈 상태 행에 중복 버튼 없음)
    expect(screen.queryByRole("button", { name: /연결 방법/ })).toBeNull();
    expect(document.querySelector(".usage-empty-rows")!.textContent).not.toMatch(/연결 방법/);
    expect(document.querySelector(".usage-empty-rows")!.textContent).not.toMatch(/`/);
  });

  it("탭으로 상황을 고르고 쉘을 바꾸며 복사하면 2초간 '복사됨'이 보인다", async () => {
    const writes: string[] = [];
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (t: string) => void writes.push(t) } });
    mount({ getUsage: async () => emptyReport(), listUsageSources: async () => [setupSource()] });
    const guide = await screen.findByRole("region", { name: "상태 줄 연결 안내" });
    fireEvent.click(within(guide).getByRole("tab", { name: "이미 써요" }));
    expect(within(guide).getByText(/bash-snippet/)).toBeTruthy();
    fireEvent.change(within(guide).getByRole("combobox"), { target: { value: "powershell" } });
    expect(within(guide).getByText(/ps-snippet/)).toBeTruthy();
    fireEvent.click(within(guide).getByRole("button", { name: /^복사/ }));
    expect(await within(guide).findByRole("button", { name: /복사됨/ })).toBeTruthy();
    expect(writes[0]).toContain("ps-snippet");
  });

  it("test_only 출처는 '개발용' 접힘 안에만 있고 빈 상태 줄에 나오지 않는다", async () => {
    mount({ getUsage: async () => emptyReport(), listUsageSources: async () => [sources[0]!, devSource] });
    await screen.findByText("아직 값이 없습니다");
    const dev = screen.getByText(/^개발용 \(1\)/).closest("details")!;
    expect(within(dev).getByText("시험 출처")).toBeTruthy();
    expect(screen.getAllByText("시험 출처")).toHaveLength(1);
  });

  it("값이 있으면 안내는 접혀 있고 마지막 수신 시각이 요약에 보인다", async () => {
    mount({ listUsageSources: async () => [sources[0]!, setupSource({ last_received_at: now - 120 })], getUsage: async () => report({ windows: [{ source: "src-setup", window: "w", used_ratio: 0.2, observed_at: now - 120 }] }) });
    const guide = await screen.findByRole("region", { name: "상태 줄 연결 안내" });
    expect(guide.querySelector("details")!.hasAttribute("open")).toBe(false);
    expect(guide.textContent).toMatch(/상태 줄 연결됨 · 마지막 수신/);
  });

  it("[다시 확인]은 사용량과 출처를 다시 조회한다", async () => {
    let calls = 0;
    mount({ getUsage: async () => { calls += 1; return emptyReport(); }, listUsageSources: async () => [setupSource()] });
    const guide = await screen.findByRole("region", { name: "상태 줄 연결 안내" });
    await waitFor(() => expect(calls).toBeGreaterThan(0));
    const before = calls;
    fireEvent.click(within(guide).getByRole("button", { name: "다시 확인" }));
    await waitFor(() => expect(calls).toBeGreaterThan(before));
  });
});
