import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BackendDescriptor, BackendReadiness } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { TestI18n } from "../../testing/TestI18n";
import { READINESS_TONES } from "../backendReadiness";
import { BackendConnectChip } from "./BackendConnectChip";
import { BackendConnectIcon, badgeStatus } from "./BackendConnectBadge";
import { useBackendConnectSummary, useOpenBackendConnect } from "./context";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "#");
});
const LONG = { timeout: 15_000 };
const NOW = Date.now() / 1000;

// 백엔드 id·문구는 전부 임의 값이다.
const capable = (id: string, title: string, extra: Partial<BackendDescriptor> = {}): BackendDescriptor => ({ id, title, capabilities: { status: true, probe: true, login: true }, ...extra }) as BackendDescriptor;
const status = (id: string, tone: string, short: string, extra: Partial<BackendReadiness> = {}): BackendReadiness => ({ backend_id: id, state: "zz", tone: tone as never, summary: `${short} 전체 요약`, short_summary: short, checked_at: NOW, ...extra });

function mount(overrides: Record<string, unknown> = {}, path = "/usage") {
  const fake = createFakeClients({
    listBackends: vi.fn(async () => [capable("be-1", "백엔드 하나"), capable("be-2", "백엔드 둘")]),
    listBackendStatuses: vi.fn(async () => [status("be-1", "ok", "준비 끝"), status("be-2", "error", "로그인 필요")]),
    ...overrides,
  });
  mountApp(fake.clients, path);
  return fake;
}
const button = () => screen.findByTestId("backend-connect-button", {}, LONG);

describe("도구줄 단추", () => {
  it("맨 앞에 있고 aria-label = 툴팁 문구이며 대표 백엔드(가장 나쁜 톤)의 이름과 짧은 상태를 담는다", async () => {
    mount();
    const btn = await button();
    const label = btn.getAttribute("aria-label");
    expect(label).toBe("백엔드 연결: 백엔드 둘 — 로그인 필요");
    expect(btn.closest(".ac-tip-host")?.querySelector(".ac-tip")?.textContent).toBe(label);
    expect(btn.getAttribute("data-tone")).toBe("error");
    const tools = btn.closest(".ac-sidebar-tools");
    expect(tools).not.toBeNull();
    // 도움말 앞(도구줄 맨 앞)
    expect(tools?.querySelector("button")).toBe(btn);
  });

  it("공통 설정의 기본 백엔드가 보이는 목록에 있으면 그 백엔드의 톤을 쓴다", async () => {
    const fake = createFakeClients({
      listBackends: vi.fn(async () => [capable("be-1", "백엔드 하나"), capable("be-2", "백엔드 둘")]),
      listBackendStatuses: vi.fn(async () => [status("be-1", "ok", "준비 끝"), status("be-2", "error", "로그인 필요")]),
    });
    fake.rest.getSettingsVersioned.mockImplementation(async () => ({ value: { agent_defaults: { backend: "be-1" } }, version_hash: "h" }));
    mountApp(fake.clients, "/usage");
    await waitFor(() => expect(screen.getByTestId("backend-connect-button").getAttribute("aria-label")).toBe("백엔드 연결: 백엔드 하나 — 준비 끝"), LONG);
  });

  it("상태 점검·연결 테스트 능력이 있는 백엔드가 없으면 단추·사용량 칩·명령이 모두 없다", async () => {
    mount({ listBackends: vi.fn(async () => [{ id: "be-x", title: "능력 없음", capabilities: { status: false, probe: false } }]), listBackendStatuses: vi.fn(async () => []) });
    await screen.findByRole("navigation", { name: "주 메뉴" }, LONG);
    await waitFor(() => expect(screen.queryByTestId("backend-connect-slot")).toBeNull(), LONG);
    expect(screen.queryByTestId("backend-connect-button")).toBeNull();
    expect(screen.queryByTestId("backend-connect-chip")).toBeNull();
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    const palette = await screen.findByRole("dialog", { name: "빠른 이동" }, LONG);
    expect(within(palette).queryByText("백엔드 연결…")).toBeNull();
  });

  it("준비 상태 경로가 없으면(404) 숨긴다", async () => {
    const { ApiError } = await import("@agent-console/api-client");
    mount({ listBackendStatuses: vi.fn(async () => { throw new ApiError(404, { code: "not_found", message: "없음" }); }) });
    await screen.findByRole("navigation", { name: "주 메뉴" }, LONG);
    await waitFor(() => expect(screen.queryByTestId("backend-connect-slot")).toBeNull(), LONG);
    expect(screen.queryByTestId("backend-connect-button")).toBeNull();
  });

  it("누르면 모달이 열리고 Esc로 닫으면 단추로 초점이 돌아온다", async () => {
    mount();
    const btn = await button();
    btn.focus();
    fireEvent.click(btn);
    const dialog = await screen.findByRole("dialog", { name: "백엔드 연결" }, LONG);
    expect(await within(dialog).findByTestId("backend-readiness-be-2", {}, LONG)).toBeTruthy();
    // 기본 백엔드가 없으면 서버 순서
    expect(within(dialog).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["백엔드 하나", "백엔드 둘"]);
    expect(within(dialog).getByRole("link", { name: /설정에서 자세히/ }).getAttribute("href")).toBe("/settings#common/backend-readiness");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "백엔드 연결" })).toBeNull(), LONG);
    expect(document.activeElement).toBe(btn);
  });

  it("[설정에서 자세히]는 모달을 닫고 설정의 준비 상태 제목으로 스크롤·초점을 준다", async () => {
    mount();
    const dialog = await (async () => {
      fireEvent.click(await button());
      return screen.findByRole("dialog", { name: "백엔드 연결" }, LONG);
    })();
    fireEvent.click(within(dialog).getByRole("link", { name: /설정에서 자세히/ }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "백엔드 연결" })).toBeNull(), LONG);
    const heading = await screen.findByRole("heading", { name: "백엔드 인증·실행 준비" }, LONG);
    expect(heading.id).toBe("backend-readiness");
    expect(heading.getAttribute("tabindex")).toBe("-1");
    await waitFor(() => expect(document.activeElement).toBe(heading), LONG);
  });
});

describe("모달 겹침", () => {
  it("로그인 확인 대화상자가 모달 위에 겹치고 Esc는 맨 위 층 하나만 닫는다", async () => {
    mount({ listBackendStatuses: vi.fn(async () => [status("be-1", "warn", "로그인 안 됨", { actions: [{ kind: "login", label: "구독으로 로그인", primary: true }] }), status("be-2", "ok", "좋음")]) });
    fireEvent.click(await button());
    const dialog = await screen.findByRole("dialog", { name: "백엔드 연결" }, LONG);
    fireEvent.click(await within(dialog).findByRole("button", { name: "구독으로 로그인" }, LONG));
    const dialogs = await screen.findAllByRole("dialog", {}, LONG);
    expect(dialogs.length).toBe(2);
    const top = dialogs[dialogs.length - 1]!;
    fireEvent.keyDown(top, { key: "Escape" });
    await waitFor(() => expect(screen.getAllByRole("dialog").length).toBe(1), LONG);
    expect(screen.getByRole("dialog", { name: "백엔드 연결" })).toBeTruthy();
  });
});

describe("Ctrl+K 명령", () => {
  it("'백엔드 연결…'이 현재 상태 부제와 함께 보이고, 고르면 모달이 열리며 닫으면 단추로 초점이 간다", async () => {
    mount();
    const btn = await button();
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    const palette = await screen.findByRole("dialog", { name: "빠른 이동" }, LONG);
    const item = await within(palette).findByText("백엔드 연결…", {}, LONG);
    expect(item.closest("[role=option]")?.textContent).toContain("문제");
    fireEvent.click(item);
    const dialog = await screen.findByRole("dialog", { name: "백엔드 연결" }, LONG);
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "백엔드 연결" })).toBeNull(), LONG);
    await waitFor(() => expect(document.activeElement).toBe(btn), LONG);
  });

  it("별칭(영어 sign in)으로도 찾힌다", async () => {
    mount();
    await button();
    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    const palette = await screen.findByRole("dialog", { name: "빠른 이동" }, LONG);
    fireEvent.change(within(palette).getByRole("combobox"), { target: { value: "sign in" } });
    expect(await within(palette).findByText("백엔드 연결…", {}, LONG)).toBeTruthy();
  });
});

describe("사용량 머리 칩", () => {
  it("칩이 새로 고침 앞에 있고 누르면 같은 모달이 열린다. 아이콘·글자·툴팁이 단추와 같은 상태", async () => {
    mount();
    const chip = await screen.findByTestId("backend-connect-chip", {}, LONG);
    expect(chip.getAttribute("aria-label")).toBe("백엔드 연결: 백엔드 둘 — 로그인 필요");
    expect(chip.textContent).toContain("로그인 필요");
    expect(chip.nextElementSibling?.getAttribute("aria-label")).toBe("새로 고침");
    fireEvent.click(chip);
    expect(await screen.findByRole("dialog", { name: "백엔드 연결" }, LONG)).toBeTruthy();
  });
});

describe("배지 모양", () => {
  const tones = ["ok", "warn", "error", "unknown", "checking"] as const;
  it("다섯 상태의 모양(아이콘 이름)이 서로 모두 다르다 — 색을 지워도 구별된다", () => {
    const shapes = tones.map((t) => badgeStatus(t));
    expect(new Set(shapes).size).toBe(tones.length);
    expect(READINESS_TONES.warn.icon).not.toBe(READINESS_TONES.unknown.icon);
    // 조회 실패는 unknown과 같은 모양(상태 이름만 다르다)
    expect(badgeStatus("unavailable")).toBe(badgeStatus("unknown"));
  });

  it("렌더된 StatusIcon의 data-status가 상태마다 다르다", () => {
    const { container } = render(
      <>
        {tones.map((t) => (
          <BackendConnectIcon key={t} tone={t} />
        ))}
      </>,
    );
    const got = Array.from(container.querySelectorAll(".ac-status-icon")).map((e) => e.getAttribute("data-status"));
    expect(new Set(got).size).toBe(5);
  });

  it("칩은 props만으로 그려지고 글자·aria-label·클릭을 가진다", () => {
    const onClick = vi.fn();
    render(
      <TestI18n>
        <BackendConnectChip tone="warn" summary="주의 상태" label="백엔드" tip="전체 툴팁" onClick={onClick} />
      </TestI18n>,
    );
    const chip = screen.getByRole("button", { name: "전체 툴팁" });
    expect(chip.textContent).toContain("주의 상태");
    fireEvent.click(chip);
    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("공급자 밖(사용량 화면 단독 사용)", () => {
  it("모달 여는 함수도 상태 요약도 없어서 아무것도 그리지 않아도 깨지지 않는다", () => {
    function Probe() {
      const open = useOpenBackendConnect();
      const summary = useBackendConnectSummary();
      return <p data-testid="probe">{`${open === undefined}/${summary === undefined}`}</p>;
    }
    render(<Probe />);
    expect(screen.getByTestId("probe").textContent).toBe("true/true");
  });
});
