import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo, RunEvent } from "@agent-console/contracts";
import type { MemoryEntrySummary, MemoryScopeKindInfo } from "@agent-console/contracts/memory";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { ModulesProvider } from "../../modules";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { makeEntries } from "@agent-console/memory-view/testing";
import { RunMemoryChips } from "../memory";
import { buildKindRows, entriesByKind, kindActions } from "./kindRows";
import { ScopeKindWidget } from "./ScopeKindWidget";

afterEach(cleanup);
vi.setConfig({ testTimeout: 40_000 });
const LONG = { timeout: 15_000 };

// 범위 종류 id·라벨·규칙 id는 모두 이 테스트 안의 임의 값이다. 화면 코드는 이 이름을 모른다.
const mod = (id: string, roles: string[]): ModuleInfo => ({ id, kind: "k", version: "1.0.0", status: "active", web_roles: roles, provides: [] });
const KINDS: MemoryScopeKindInfo[] = [
  { kind: "k-base", label: "기본 하나", id: "", origin: "default", context_fields: [] },
  { kind: "k-plug", label: "플러그 둘", id: "{/graph_id}", origin: "plugin:demo-pack", context_fields: ["graph_id"] },
  { kind: "k-mine", label: "내 종류", id: "{/project_id}", origin: "user", context_fields: ["project_id"] },
];
const SCOPES = [
  { scope: { kind: "k-mine", id: "p1" }, entries: 4, kind_known: true },
  { scope: { kind: "k-mine", id: "p2" }, entries: 2, kind_known: true },
];
const RULE = { id: "r-old", when: {}, action: "archive", description: "오래된 임시" };

function mount(modules: ModuleInfo[], settings: Record<string, unknown> = {}, rest: Record<string, unknown> = {}) {
  const { clients, rest: r } = createFakeClients({
    listModules: vi.fn(async () => modules),
    getSettingsVersioned: vi.fn(async () => ({ value: settings, version_hash: "s1" })),
    listMemoryScopeKinds: vi.fn(async () => ({ kinds: KINDS, include_defaults: true })),
    listMemoryScopes: vi.fn(async () => SCOPES),
    checkMemorySettings: vi.fn(async () => []),
    getModuleOptions: vi.fn(async () => ({ module_id: "m-mem", values: { max_entry_bytes: 65_536, retention_interval_seconds: 3600 } })),
    ...rest,
  });
  mountApp(clients, "/settings#memory");
  return r;
}
const MEM = [mod("m-s", ["settings"]), mod("m-mem", ["memory"])];

describe("kindRows(순수 함수)", () => {
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  it("초안이 객체면 사용자 종류(덮어쓰기), null이면 끔, 키가 없으면 원래 종류로 돌아간다", () => {
    const counts = entriesByKind(SCOPES as never);
    const out = buildKindRows(KINDS, { "k-base": { label: "바꿈" }, "k-plug": null }, {}, true, counts, same);
    expect(out.rows.map((r) => [r.id, r.origin, r.overrides, r.label])).toEqual([
      ["k-base", "user", "default", "바꿈"],
      ["k-mine", "user", undefined, "내 종류"],
    ]);
    expect(out.disabled.map((r) => r.id)).toEqual(["k-plug"]);
    expect(out.rows.find((r) => r.id === "k-mine")?.entries).toBe(6);
  });
  it("기본 사용이 꺼져 있으면 기본 출처 종류가 빠진다. 행 동작은 출처로 정해진다", () => {
    const out = buildKindRows(KINDS, {}, {}, false, new Map(), same);
    expect(out.rows.map((r) => r.id)).toEqual(["k-plug", "k-mine"]);
    expect(kindActions({ origin: "default", overrides: undefined, disabled: false })).toEqual(["view", "clone", "disable"]);
    expect(kindActions({ origin: "user", overrides: undefined, disabled: false })).toEqual(["edit", "remove"]);
    expect(kindActions({ origin: "user", overrides: "default", disabled: false })).toEqual(["edit", "revert"]);
    expect(kindActions({ origin: "default", overrides: undefined, disabled: true })).toEqual(["enable"]);
  });
});

describe("설정 › 메모리 섹션", () => {
  it("메모리 역할이 없으면 섹션도 서버 호출도 없다", async () => {
    const rest = mount([mod("m-s", ["settings"])]);
    await screen.findByRole("navigation", { name: /섹션/ }, LONG);
    await waitFor(() => expect(screen.getByRole("link", { name: "채팅" })).toBeTruthy(), LONG);
    expect(screen.queryByRole("link", { name: "메모리" })).toBeNull();
    expect(screen.queryByTestId("memset")).toBeNull();
    expect(rest["listMemoryScopeKinds"]).not.toHaveBeenCalled();
  });

  it("범위 종류 표는 서버 데이터로 그려지고 출처 배지·항목 수·행 동작이 출처에 따라 다르다", async () => {
    mount(MEM);
    const table = await screen.findByTestId("memset-kinds", {}, LONG);
    const base = (await within(table).findByText("기본 하나", {}, LONG)).closest("li") as HTMLElement;
    expect(within(base).getByText("기본")).toBeTruthy();
    expect(within(base).getByText("(비어 있음 — 범위 id 없음)")).toBeTruthy();
    expect(within(base).getByRole("button", { name: "복제해서 고치기" })).toBeTruthy();
    const plug = within(table).getByText("플러그 둘").closest("li") as HTMLElement;
    expect(within(plug).getByText("플러그인: demo-pack")).toBeTruthy();
    const mine = within(table).getByText("내 종류").closest("li") as HTMLElement;
    expect(within(mine).getByText("사용자")).toBeTruthy();
    expect(within(mine).getByText("6")).toBeTruthy();
    expect(within(mine).getByRole("button", { name: "편집" })).toBeTruthy();
    expect(within(mine).queryByRole("button", { name: "끄기" })).toBeNull();
  });

  it("항목이 없는 기본 종류는 바로 꺼지고(null 저장), 항목이 있는 종류는 확인 창을 거친다", async () => {
    const rest = mount(MEM);
    const table = await screen.findByTestId("memset-kinds", {}, LONG);
    const base = (await within(table).findByText("기본 하나", {}, LONG)).closest("li") as HTMLElement;
    fireEvent.click(within(base).getByRole("button", { name: "끄기" }));
    await waitFor(() => expect(within(screen.getByTestId("memset-kinds")).queryByText("기본 하나")).toBeNull());
    const mine = within(table).getByText("내 종류").closest("li") as HTMLElement;
    fireEvent.click(within(mine).getByRole("button", { name: "지우기" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/이 종류의 항목 6개는 남습니다/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    expect(within(table).getByText("내 종류")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(rest["putSettingsVersioned"]).toHaveBeenCalled());
    const saved = (rest["putSettingsVersioned"] as ReturnType<typeof vi.fn>).mock.calls[0]![0] as { memory: { scope_kinds: Record<string, unknown> } };
    expect(saved.memory.scope_kinds).toEqual({ "k-base": null });
  });

  it("새 범위 종류: 검사가 error를 내면 [적용]이 꺼지고, 문제가 없으면 초안에 들어간다", async () => {
    const check = vi.fn(async (section: Record<string, unknown>) => {
      const kinds = (section["scope_kinds"] ?? {}) as Record<string, { label?: string }>;
      return Object.values(kinds).some((k) => k.label === "나쁨") ? [{ severity: "error" as const, code: "x", message: "틀이 잘못되었습니다", path: "/memory/scope_kinds/k-new" }] : [];
    });
    mount(MEM, {}, { checkMemorySettings: check });
    await screen.findByTestId("memset-kinds", {}, LONG);
    fireEvent.click(screen.getByRole("button", { name: /새 범위 종류/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("라벨"), { target: { value: "나쁨" } });
    fireEvent.change(within(dialog).getByLabelText("id"), { target: { value: "k-new" } });
    expect(await within(dialog).findByText("틀이 잘못되었습니다", {}, LONG)).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: "적용" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText("라벨"), { target: { value: "좋음" } });
    await waitFor(() => expect((within(dialog).getByRole("button", { name: "적용" }) as HTMLButtonElement).disabled).toBe(false), LONG);
    fireEvent.click(within(dialog).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(within(screen.getByTestId("memset-kinds")).getByText("좋음")).toBeTruthy());
  });

  it("비밀 처리는 스키마 enum의 선택지(거부·가리고 저장)이고 설치자 한도는 서버 값 그대로 읽기 전용이다", async () => {
    mount(MEM);
    const group = await screen.findByRole("radiogroup", { name: /비밀/ }, LONG);
    expect(within(group).getAllByRole("radio")).toHaveLength(2);
    expect((within(group).getByRole("radio", { name: /저장 거부/ }) as HTMLInputElement).checked).toBe(true);
    expect(within(group).getByText("비밀을 그대로 저장하는 선택지는 없습니다.")).toBeTruthy();
    fireEvent.click(screen.getByText("설치자 한도 (읽기 전용)"));
    expect(await screen.findByText("65536", {}, LONG)).toBeTruthy();
    expect(screen.getByText("max_entry_bytes")).toBeTruthy();
  });

  it("정리 규칙이 없으면 빈 상태 안내가 나오고 기본 규칙은 없다", async () => {
    mount(MEM);
    const panel = await screen.findByTestId("memset-retention", {}, LONG);
    expect(within(panel).getByText("정리 규칙이 없습니다")).toBeTruthy();
    expect(within(panel).getByText("아무것도 자동으로 보관하거나 지우지 않습니다.")).toBeTruthy();
    expect((within(panel).getByRole("button", { name: "미리보기" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("정리 미리보기·적용", () => {
  const updated = Math.floor(Date.now() / 1000) - 3 * 86_400;
  const entry: MemoryEntrySummary = { ...makeEntries(1)[0]!, id: "e1", scope: { kind: "k-mine", id: "p1" }, key: "메모/임시", updated_at: updated, bytes: 410 };
  const rules = { retention: { rules: [RULE] } };
  // 5.7R.28: 계획 항목이 마지막 쓰기·크기를 싣는다(목록 질의로 채우지 않는다).
  const plan = { count: 1, excluded_pinned: 2, items: [{ entry_id: "e1", scope: { kind: "k-mine", id: "p1" }, key: "메모/임시", version: 1, rule: "r-old", action: "archive" as const, updated_at: entry.updated_at, bytes: entry.bytes }] };
  const base = () => ({
    planMemoryRetention: vi.fn(async () => plan),
    applyMemoryRetention: vi.fn(async () => ({ archived: 1, deleted: 0, skipped: 0 })),
  });

  it("[미리보기]는 초안 규칙을 본문으로 주고 표에 규칙·동작·범위·키·마지막 쓰기·크기가 나온다. 적용은 확인 창을 거친다", async () => {
    const rest = mount(MEM, { memory: rules }, base());
    const panel = await screen.findByTestId("memset-retention", {}, LONG);
    expect(within(panel).getByText("오래된 임시")).toBeTruthy();
    expect(within(panel).getByText("자동 실행: 1시간마다")).toBeTruthy();
    expect((within(panel).getByRole("button", { name: "지금 적용" }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(panel).getByText("미리보기를 먼저 하세요.")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: "미리보기" }));
    await waitFor(() => expect(rest["planMemoryRetention"]).toHaveBeenCalledWith({ rules: [RULE], limit: 200 }));
    const table = await within(panel).findByRole("table", { name: "정리 대상 표" }, LONG);
    await waitFor(() => expect(within(table).getByText("3일 전")).toBeTruthy(), LONG);
    expect(within(table).getByText("메모/임시")).toBeTruthy();
    expect(within(table).getByText("r-old")).toBeTruthy();
    expect(within(table).getByText("410 B")).toBeTruthy();
    expect(within(panel).getByText(/고정 2개 제외/)).toBeTruthy();
    const apply = within(panel).getByRole("button", { name: "지금 적용" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(false);
    fireEvent.click(apply);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/1개를 처리합니다: 보관 1, 지우기\(표시 삭제\) 0/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(rest["applyMemoryRetention"]).toHaveBeenCalledTimes(1));
    expect(await within(panel).findByText(/보관 1 · 지움 0 · 건너뜀 0/, {}, LONG)).toBeTruthy();
  });

  it("규칙을 바꾸면(저장 전 변경) [지금 적용]이 꺼지고 먼저 저장하라는 이유를 쓴다", async () => {
    mount(MEM, { memory: { retention: { rules: [RULE, { ...RULE, id: "r-two" }] } } }, base());
    const panel = await screen.findByTestId("memset-retention", {}, LONG);
    fireEvent.click(within(panel).getByRole("button", { name: "미리보기" }));
    await within(panel).findByRole("table", { name: "정리 대상 표" }, LONG);
    fireEvent.click(within(panel).getByRole("button", { name: "r-two 위로 옮기기" }));
    await waitFor(() => expect(within(panel).getByText("먼저 저장하세요.")).toBeTruthy());
    expect((within(panel).getByRole("button", { name: "지금 적용" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("ScopeKindWidget", () => {
  const props = { id: "w", label: "범위 종류", required: true, disabled: false, readonly: false, onBlur: () => undefined, schema: {}, options: {}, errors: [] as string[] };
  const host = (modules: ModuleInfo[], value: unknown, onChange = vi.fn(), rest: Record<string, unknown> = {}) => {
    const { clients, rest: r } = createFakeClients({ listModules: vi.fn(async () => modules), listMemoryScopeKinds: vi.fn(async () => ({ kinds: [...KINDS, { kind: "k-off", label: "끈 종류", origin: "user", disabled: true }], include_defaults: true })), ...rest });
    render(
      <ApiProvider clients={clients}>
        <QueryClientProvider client={createAppQueryClient({ retry: false })}>
          <ModulesProvider subscribeSignals={() => () => undefined}>
            <ScopeKindWidget {...props} value={value} onChange={onChange} />
          </ModulesProvider>
        </QueryClientProvider>
      </ApiProvider>,
    );
    return { rest: r, onChange };
  };

  it("선택지는 서버가 준 켜진 종류이고(끈 종류 제외), 고르면 id가 값이 된다", async () => {
    const { onChange } = host(MEM, "k-plug");
    const select = (await screen.findByRole("combobox", { name: "범위 종류" }, LONG)) as HTMLSelectElement;
    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(2), LONG);
    const labels = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(labels).toContain("내 종류 (k-mine)");
    expect(labels.join()).not.toContain("끈 종류");
    fireEvent.change(select, { target: { value: "k-mine" } });
    expect(onChange).toHaveBeenCalledWith("k-mine");
  });

  it("목록에 없는 id는 id를 그대로 보이고 '알 수 없는 범위 종류' 표지를 단다", async () => {
    host(MEM, "k-gone");
    expect(await screen.findByText("알 수 없는 범위 종류", {}, LONG)).toBeTruthy();
    expect((screen.getByRole("combobox", { name: "범위 종류" }) as HTMLSelectElement).value).toBe("k-gone");
  });

  it("메모리 기능이 꺼져 있으면 목록을 부르지 않고 id 직접 입력 + 안내로 떨어진다", async () => {
    const { rest } = host([mod("m-s", ["settings"])], "k-x");
    expect(await screen.findByText(/메모리 기능이 꺼져 있어 목록을 불러올 수 없습니다/, {}, LONG)).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "범위 종류" }) as HTMLInputElement).value).toBe("k-x");
    expect(rest["listMemoryScopeKinds"]).not.toHaveBeenCalled();
  });
});

describe("실행 요약 칩", () => {
  const ev = (seq: number, type: string, status = "ok"): RunEvent => ({ seq, ts: 1, run_id: "run-1", type, payload: { op: type.slice(7), status } }) as unknown as RunEvent;
  const view = (events: RunEvent[], onOpenReads = vi.fn()) => {
    const { clients, rest } = createFakeClients({ listRunEvents: vi.fn(async () => events) });
    const out = render(
      <ApiProvider clients={clients}>
        <QueryClientProvider client={createAppQueryClient({ retry: false })}>
          <MemoryRouter>
            <RunMemoryChips runId="run-1" active={false} onOpenReads={onOpenReads} />
          </MemoryRouter>
        </QueryClientProvider>
      </ApiProvider>,
    );
    return { rest, onOpenReads, ...out };
  };

  it("쓰기·읽기 수와 실패 수를 이벤트 type 접두(memory.)로 세고, 쓰기 칩은 author_run 링크다", async () => {
    const { rest, onOpenReads } = view([ev(1, "memory.write"), ev(2, "memory.write", "conflict"), ev(3, "memory.delete"), ev(4, "memory.read"), ev(5, "memory.search"), ev(6, "memory.access_invalid")]);
    const write = await screen.findByRole("link", { name: "메모리 쓰기 3" }, LONG);
    expect(write.getAttribute("href")).toBe("/memory?author_run=run-1");
    expect(rest["listRunEvents"]).toHaveBeenCalledWith("run-1", { type_prefix: "memory." });
    expect(screen.getByText("실패 1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "메모리 읽기 2" }));
    expect(onOpenReads).toHaveBeenCalledWith("memory.read");
  });

  it("메모리 이벤트가 하나도 없으면 칩이 없고, 200개를 넘으면 200+로 보인다", async () => {
    const none = view([]);
    await waitFor(() => expect(none.rest["listRunEvents"]).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("group", { name: "메모리 사용" })).toBeNull();
    cleanup();
    view(Array.from({ length: 205 }, (_, i) => ev(i, "memory.write")));
    expect(await screen.findByRole("link", { name: "메모리 쓰기 200+" }, LONG)).toBeTruthy();
  });
});
