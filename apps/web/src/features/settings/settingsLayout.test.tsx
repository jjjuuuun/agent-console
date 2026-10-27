import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { ModulesSectionView } from "./sections/ModulesSection";
import { ModuleOptionsReadOnly } from "./sections/ModuleOptionsPanel";
import { moduleCommandSnippet } from "./modulesView";

afterEach(cleanup);

const mod = (id: string, status: string, extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id, kind: "k", version: "1.0.0", status, web_roles: [], provides: [], ...extra });

describe("설정 화면: 섹션 하나씩", () => {
  it("묶음 제목 아래 목록이 나오고 본문에는 선택한 섹션 하나만 있다", async () => {
    mountApp(createFakeClients().clients, "/settings#chat");
    const nav = await screen.findByRole("navigation", { name: "설정 섹션" });
    for (const g of ["자주 쓰는", "실행 기본값", "데이터", "시스템"]) expect(await within(nav).findByRole("heading", { name: g })).toBeTruthy();
    expect(await screen.findByRole("region", { name: "채팅" })).toBeTruthy();
    expect(document.querySelectorAll(".app-settings-section")).toHaveLength(1);
    expect(within(nav).getByRole("link", { name: "채팅" }).getAttribute("aria-current")).toBe("location");
  });

  it("공통 설정의 이름은 에이전트 기본값이다", async () => {
    mountApp(createFakeClients().clients, "/settings#common");
    expect(await screen.findByRole("region", { name: "에이전트 기본값" })).toBeTruthy();
    expect(screen.queryByText("공통 설정")).toBeNull();
  });

  it("해시가 없으면 첫 섹션, 목록 항목을 누르면 그 섹션으로 바뀐다", async () => {
    mountApp(createFakeClients().clients, "/settings");
    const nav = await screen.findByRole("navigation", { name: "설정 섹션" });
    expect(await screen.findByRole("region", { name: "화면" })).toBeTruthy();
    fireEvent.click(await within(nav).findByRole("link", { name: "서버 정보" }));
    expect(await screen.findByRole("region", { name: "서버 정보" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "화면" })).toBeNull();
    expect(window.location.hash).toBe("#server");
  });

  it("값을 바꾸면 섹션 머리에 변경 수가 보이고 목록 항목에 점이 붙는다", async () => {
    mountApp(createFakeClients().clients, "/settings#chat");
    const chat = await screen.findByRole("region", { name: "채팅" });
    fireEvent.click(await within(chat).findByRole("radio", { name: /거절/ }));
    expect(await within(chat).findByText("저장되지 않은 변경 1")).toBeTruthy();
    const nav = screen.getByRole("navigation", { name: "설정 섹션" });
    expect(within(within(nav).getByRole("link", { name: /채팅/ })).getByRole("img", { name: "저장되지 않은 변경 있음" })).toBeTruthy();
  });

  it("서버 정보: 키-값 표 + 접힌 플러그인(종류별 표)", async () => {
    mountApp(createFakeClients().clients, "/settings#server");
    const table = await screen.findByRole("table", { name: "서버 정보" });
    expect(within(table).getByText("서버 버전")).toBeTruthy();
    expect(within(table).queryByText("로드된 플러그인")).toBeNull();
    const summary = screen.getByText("로드된 플러그인 1개");
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.getAttribute("data-open")).toBe("false");
    fireEvent.click(summary);
    const plugins = await screen.findByRole("table", { name: "로드된 플러그인" });
    expect(within(plugins).getByText("grp")).toBeTruthy();
    expect(within(plugins).getByText(/plug-a/)).toBeTruthy();
  });
});

describe("기능 모듈 섹션: 명령 조각·옵션", () => {
  it("켜진 모듈은 끄는 조각, 꺼진 모듈은 켜는 조각을 만든다", () => {
    expect(moduleCommandSnippet({ id: "m-a", status: "active" })).toContain("--disable-module m-a");
    const off = moduleCommandSnippet({ id: "m-b", status: "disabled" });
    expect(off).toContain("--enable-module m-b");
  });

  it("펼친 행에 명령 조각 복사와 옵션 영역이 있고 옵션 쓰기 컨트롤은 없다", async () => {
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(
      <MemoryRouter>
        <ModulesSectionView
          state={{ phase: "ready", modules: [mod("m-a", "active", { provides: ["port.one"] })] }}
          refetching={false}
          onRefresh={() => {}}
          screens={[]}
          parts={[]}
          renderOptions={(m) => <ModuleOptionsReadOnly view={{ module_id: m.id, schema: { type: "object", properties: { level: { type: "integer", title: "수준" } } }, values: { level: 3 }, yaml_snippet: "modules:\n  options:\n    m-a:\n      level: 3" }} />}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("제공: port.one")).toBeTruthy();
    fireEvent.click(screen.getByRole("treeitem", { name: /m-a/ }));
    fireEvent.click(screen.getByRole("button", { name: "명령 조각 복사" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("--disable-module m-a"));
    const input = screen.getByRole("spinbutton", { name: /수준/ }) as HTMLInputElement;
    expect(input.disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "YAML 조각 복사" }));
    expect(writeText).toHaveBeenCalledWith("modules:\n  options:\n    m-a:\n      level: 3");
  });

  it("스키마를 선언하지 않은 모듈은 안내만 보인다", () => {
    render(<ModuleOptionsReadOnly view={{ module_id: "m-x", schema: null, values: {}, yaml_snippet: "" }} />);
    expect(screen.getByText("이 모듈은 옵션 스키마를 선언하지 않았습니다.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "YAML 조각 복사" })).toBeNull();
  });

  it("컨테이너는 행을 펼칠 때 서버에서 옵션을 읽는다", async () => {
    const { clients, rest } = createFakeClients({
      listModules: vi.fn(async () => [mod("m-a", "active")]),
      getModuleOptions: vi.fn(async (id: string) => ({ module_id: id, schema: null, values: {}, yaml_snippet: "" })),
    });
    mountApp(clients, "/settings#modules");
    const row = await screen.findByRole("treeitem", { name: /m-a/ });
    expect(rest["getModuleOptions"]).not.toHaveBeenCalled();
    fireEvent.click(row);
    await waitFor(() => expect(rest["getModuleOptions"]).toHaveBeenCalledWith("m-a"));
    expect(await screen.findByText("이 모듈은 옵션 스키마를 선언하지 않았습니다.")).toBeTruthy();
  });
});
