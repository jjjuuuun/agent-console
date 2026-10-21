import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { LogSourceInfo, UsageSourceInfo, WorkspaceSettings } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

afterEach(cleanup);
const LONG = { timeout: 15_000 };

// 출처·범주 이름은 임의 값이다(앱은 이 이름을 모른다).
const src = (id: string, over: { reads?: boolean; def?: boolean; enabled?: boolean; status?: LogSourceInfo["status"] } = {}): LogSourceInfo => ({
  descriptor: {
    id,
    title: `출처-${id}`,
    format: "f",
    reads_paths: over.reads ?? false,
    default_enabled: over.def ?? false,
    setup_help: "설정 방법 안내 `x`",
    docs_url: "javascript:alert(1)",
    config_schema: { type: "object", properties: { roots: { type: "array", items: { type: "string" }, title: "위치들" }, extra_opt: { type: "string", title: "추가 옵션" } } },
  },
  enabled: over.enabled ?? false,
  origin: "plugin",
  ...(over.status ? { status: over.status } : {}),
});

function mount(sources: LogSourceInfo[], settings: WorkspaceSettings = {}, rest: Record<string, unknown> = {}, section = "logs") {
  const { clients } = createFakeClients({
    getSettingsVersioned: async () => ({ value: settings, version_hash: "s1" }),
    listLogSources: async () => sources,
    getLogTaxonomy: async () => ({ categories: { "cat-z": { label: "범주 제트", tone: "danger" }, "cat-y": {} } }),
    getLogSchema: async () => {
      throw new ApiError(404, { code: "not_found", message: "x" });
    },
    listLogClassifiers: async () => [],
    ...rest,
  });
  mountApp(clients, `/settings#${section}`);
  return clients;
}

describe("설정: 로그 출처", () => {
  it("읽는 출처를 켜면 확인 다이얼로그가 뜨고 취소하면 설정이 바뀌지 않으며, 확인하면 저장 전 상태로 켜진다", async () => {
    mount([src("a", { reads: true })]);
    const card = (await screen.findByText("출처-a", {}, LONG)).closest("[data-source-card]") as HTMLElement;
    const sw = within(card).getByRole("checkbox", { name: /켜기/ });
    expect((sw as HTMLInputElement).checked).toBe(false);
    fireEvent.click(sw);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain("대화 원문이 포함될 수 있습니다");
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect((sw as HTMLInputElement).checked).toBe(false);
    fireEvent.click(sw);
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "켜기" }));
    await waitFor(() => expect((sw as HTMLInputElement).checked).toBe(true));
    expect(card.textContent).toContain("저장하면 적용됩니다");
    // 설정이 dirty이면 [지금 수집]은 막힌다(서버는 저장된 설정만 읽는다)
    expect((within(card).getByRole("button", { name: "지금 수집" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("읽지 않는 출처는 확인 없이 켜지고, http가 아닌 문서 주소는 링크가 아니다. 상태 줄은 서버 오류 코드·남은 양을 그대로 보인다", async () => {
    mount([src("b", { enabled: true, status: { last_scan_at: 1, refs: 3, pending_bytes: 2048, error_code: null } }), src("c", { enabled: true, status: { last_scan_at: 1, error_code: "x.err_code" } })], { logs: { sources: [{ id: "b", enabled: true }, { id: "c", enabled: true }] } });
    const b = (await screen.findByText("출처-b", {}, LONG)).closest("[data-source-card]") as HTMLElement;
    expect(b.textContent).toContain("남은 2.0 KB");
    const c = screen.getByText("출처-c").closest("[data-source-card]") as HTMLElement;
    expect(c.textContent).toContain("x.err_code");
    fireEvent.click(within(b).getByRole("button", { name: /설정 펼치기/ }));
    expect(b.querySelector("a[href^='javascript']")).toBeNull();
    expect(b.textContent).toContain("javascript:alert(1)");
    expect(b.textContent).toContain("외부 설정 파일");
  });

  it("서버 422 issues의 문서 기준 경로(/logs/sources/0/config/…)가 그 출처 설정 필드의 오류로 표시된다", async () => {
    mount([src("a", { enabled: true })], { logs: { sources: [{ id: "a", enabled: true, config: { roots: ["/x"] } }] } }, {
      putSettingsVersioned: async () => {
        throw new ApiError(422, { code: "validation_failed", message: "검증 실패", details: { issues: [{ severity: "error", code: "x", path: "/logs/sources/0/config/extra_opt", message: "옵션 값이 틀렸습니다" }] } });
      },
    });
    const card = (await screen.findByText("출처-a", {}, LONG)).closest("[data-source-card]") as HTMLElement;
    fireEvent.click(within(card).getByRole("checkbox", { name: /켜기/ }));
    fireEvent.click(within(card).getByRole("checkbox", { name: /켜기/ }));
    fireEvent.click(within(card).getByRole("checkbox", { name: /켜기/ }));
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(card.textContent).toContain("옵션 값이 틀렸습니다"), LONG);
  });

  it("사용량 출처 설정의 422 경로(/usage/sources/0/config/…)도 그 출처 폼 필드에 표시된다", async () => {
    const usage: UsageSourceInfo = { descriptor: { id: "u-1", title: "사용량 출처", trust: "official", config_schema: { type: "object", properties: { budget_x: { type: "number", title: "예산 엑스" } } } }, enabled: true };
    mount([], { usage: { sources: [{ id: "u-1", enabled: true, config: { budget_x: 1 } }] } }, {
      listUsageSources: async () => [usage],
      putSettingsVersioned: async () => {
        throw new ApiError(422, { code: "validation_failed", message: "검증 실패", details: { issues: [{ severity: "error", code: "usage.source_config_invalid", path: "/usage/sources/0/config/budget_x", message: "예산이 틀렸습니다" }] } });
      },
    }, "usage");
    await screen.findAllByText("사용량 출처", {}, LONG);
    const box = screen.getAllByRole("checkbox", { name: /사용량 출처/ })[0] as HTMLInputElement;
    fireEvent.click(box);
    fireEvent.click(box);
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(document.body.textContent).toContain("예산이 틀렸습니다"), LONG);
  });
});

describe("설정: 분류 체계·프로젝트 묶기", () => {
  it("분류 체계 표: 기본값 배지, 톤 선택지에 계약 어휘 전부, 이름을 바꾸면 지정됨(저장 전까지 서버 변경 없음)", async () => {
    const clients = mount([src("a", { enabled: true })]);
    const table = await screen.findByRole("grid", { name: "분류 체계 표" }, LONG).catch(async () => {
      fireEvent.click(await screen.findByText("분류 체계", {}, LONG));
      return screen.findByRole("grid", { name: "분류 체계 표" }, LONG);
    });
    const name = within(table).getByLabelText("cat-z 표시 이름") as HTMLInputElement;
    expect(name.placeholder).toBe("범주 제트");
    const tone = within(table).getByLabelText("cat-z 톤") as HTMLSelectElement;
    expect(Array.from(tone.options).map((o) => o.value)).toEqual(expect.arrayContaining(["danger", "warning", "success", "info", "neutral"]));
    fireEvent.change(name, { target: { value: "새 이름" } });
    expect(within(table).getAllByText("지정됨").length).toBeGreaterThan(0);
    expect((clients.rest as unknown as { putSettingsVersioned: { mock: { calls: unknown[] } } }).putSettingsVersioned.mock.calls).toHaveLength(0);
  });
});

describe("설정: 로그 출처 자동 켜짐(서버가 이 PC의 로그를 보고 켠 출처)", () => {
  const auto = () => mount([src("auto", { reads: true, enabled: true, status: { last_scan_at: 1, error_code: null } })]);
  const cardOf = async () => (await screen.findByText("출처-auto", {}, LONG)).closest("[data-source-card]") as HTMLElement;

  it("설정에 값이 없으면 서버가 준 켜짐을 따라 스위치가 켜져 있고 저장 전 변경이 아니며 '자동 켜짐' 표시가 있다", async () => {
    auto();
    const card = await cardOf();
    expect((within(card).getByRole("checkbox", { name: /켜기/ }) as HTMLInputElement).checked).toBe(true);
    expect(card.textContent).not.toContain("저장하면 적용됩니다");
    expect(card.textContent).toContain("기본값: 자동 켜짐");
  });

  it("사용자가 끄면 저장 전 변경이 되고 ↺로 되돌리면 다시 자동 켜짐이다", async () => {
    auto();
    const card = await cardOf();
    const sw = within(card).getByRole("checkbox", { name: /켜기/ }) as HTMLInputElement;
    fireEvent.click(sw);
    await waitFor(() => expect(sw.checked).toBe(false));
    expect(card.textContent).toContain("지정됨");
    expect(card.textContent).toContain("저장하면 적용됩니다");
    fireEvent.click(within(card).getByRole("button", { name: /기본/ }));
    await waitFor(() => expect(sw.checked).toBe(true));
    expect(card.textContent).toContain("기본값: 자동 켜짐");
  });

  it("사용자 설정이 있으면 그 값을 따른다(서버가 켜짐이어도 설정이 꺼짐이면 꺼짐)", async () => {
    mount([src("auto", { reads: true, enabled: false })], { logs: { sources: [{ id: "auto", enabled: false }] } });
    const card = await cardOf();
    expect((within(card).getByRole("checkbox", { name: /켜기/ }) as HTMLInputElement).checked).toBe(false);
    expect(card.textContent).not.toContain("자동 켜짐");
  });
});
