import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo } from "@agent-console/contracts";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import type { ModulesState } from "../../modules";
import { ModulesSectionView } from "./sections/ModulesSection";

afterEach(cleanup);

// 임의의 가짜 모듈: 종류·이름·역할은 이 테스트 안의 값이다.
const mod = (id: string, kind: string, status: string, extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id, kind, version: "1.2.3", status, web_roles: [], provides: [], ...extra });
const MODULES: ModuleInfo[] = [
  mod("m-ok", "k-one", "active", { web_roles: ["role-one"], contracts: { "c-x": "1.0.0" }, provides: ["port.one"] }),
  mod("m-bad", "k-one", "unsatisfied", { reason: "필요한 연결: port.missing", web_roles: ["role-two"] }),
  mod("m-off", "k-two", "disabled"),
  mod("m-fail", "k-two", "failed", { reason: "시작 실패 이유" }),
];

function view(state: ModulesState, extra: Partial<Parameters<typeof ModulesSectionView>[0]> = {}) {
  const onRefresh = vi.fn();
  render(
    <MemoryRouter>
      <ModulesSectionView state={state} refetching={false} onRefresh={onRefresh} screens={[{ title: "화면 하나", path: "/one", requires: ["role-one"] }]} parts={[{ id: "part-x", requires: ["role-one"] }]} {...extra} />
    </MemoryRouter>,
  );
  return { onRefresh };
}

describe("설정의 기능 모듈 섹션", () => {
  it("요약 줄과 상태별 개수, 문제 행이 그룹 맨 위에 오고 접힌 문제 행에 이유가 한 줄 보인다", () => {
    view({ phase: "ready", modules: MODULES });
    expect(screen.getByText(/켜짐/, { selector: "p" }).textContent).toMatch(/모듈 4개 — 켜짐 1 · 꺼짐 1 · 문제 2/);
    expect(screen.getByRole("radio", { name: "전체 4" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "시작 실패 1" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "충돌 0" })).toBeTruthy();
    const rows = screen.getAllByRole("treeitem").filter((el) => el.getAttribute("aria-level") === "2");
    expect(rows.map((r) => r.getAttribute("aria-label"))).toEqual(["m-bad, 연결 부족", "m-ok, 켜짐", "m-fail, 시작 실패", "m-off, 꺼짐"]);
    expect(screen.getByText("필요한 연결: port.missing")).toBeTruthy();
    expect(screen.getByText("시작 실패 이유")).toBeTruthy();
  });

  it("읽기 전용: 스위치·체크박스·저장 버튼이 없다", () => {
    view({ phase: "ready", modules: MODULES });
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /저장|켜기|끄기/ })).toBeNull();
  });

  it("상태 필터와 검색(id·역할·연결)으로 좁히고, 결과가 없으면 필터 지우기를 보인다", () => {
    view({ phase: "ready", modules: MODULES });
    fireEvent.click(screen.getByRole("radio", { name: "꺼짐 1" }));
    expect(screen.getAllByRole("treeitem").filter((el) => el.getAttribute("aria-level") === "2")).toHaveLength(1);
    fireEvent.click(screen.getByRole("radio", { name: "충돌 0" }));
    expect(screen.getByText("일치하는 모듈이 없습니다")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "필터 지우기" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "모듈 검색" }), { target: { value: "port.one" } });
    expect(screen.getAllByRole("treeitem").filter((el) => el.getAttribute("aria-level") === "2").map((r) => r.getAttribute("aria-label"))).toEqual(["m-ok, 켜짐"]);
  });

  it("행을 펼치면 버전·계약·제공 연결·영향받는 화면과 부분이 보인다(켜진 모듈의 화면은 링크)", () => {
    view({ phase: "ready", modules: MODULES });
    fireEvent.click(screen.getByRole("treeitem", { name: "m-ok, 켜짐" }));
    expect(screen.getByText("1.2.3", { selector: "dd" })).toBeTruthy();
    expect(screen.getByText("c-x 1.0.0")).toBeTruthy();
    expect(screen.getByText("port.one", { selector: "code" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "화면 하나" }).getAttribute("href")).toBe("/one");
    expect(screen.getByText("part-x")).toBeTruthy();
  });

  it("방향키로 이동하고 오른쪽 키로 펼치며 왼쪽 키로 접는다", () => {
    view({ phase: "ready", modules: MODULES });
    const first = screen.getAllByRole("treeitem")[0]!;
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    return waitFor(() => {
      const second = screen.getAllByRole("treeitem")[1]!;
      expect(document.activeElement).toBe(second);
      fireEvent.keyDown(second, { key: "ArrowRight" });
      expect(second.getAttribute("aria-expanded")).toBe("true");
      fireEvent.keyDown(second, { key: "ArrowLeft" });
      expect(second.getAttribute("aria-expanded")).toBe("false");
    });
  });

  it("조회 실패·404·빈 목록·로딩이 각각 다른 안내를 보인다", () => {
    const failed = view({ phase: "unavailable", reason: "failed" });
    expect(screen.getByText(/기능 목록을 가져오지 못했습니다/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(failed.onRefresh).toHaveBeenCalledOnce();
    cleanup();
    view({ phase: "unavailable", reason: "no-endpoint" });
    expect(screen.getByText(/이 서버는 기능 목록을 제공하지 않습니다/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
    cleanup();
    view({ phase: "ready", modules: [] });
    expect(screen.getByText("이 서버에는 켜진 기능이 없습니다.")).toBeTruthy();
    cleanup();
    view({ phase: "loading" });
    expect(screen.getByRole("status", { name: "기능 목록을 불러오는 중" })).toBeTruthy();
  });

  it("모르는 종류는 값 그대로 그룹 제목이 되고 모르는 상태는 중립 칩으로 값 그대로 보인다", () => {
    view({ phase: "ready", modules: [mod("m-x", "kind-new", "mystery")] });
    expect(screen.getByRole("treeitem", { name: /kind-new/ })).toBeTruthy();
    expect(screen.getByText("mystery")).toBeTruthy();
  });
});

describe("설정 화면의 섹션과 모듈", () => {
  it("모듈이 하나도 없으면 설정에는 기능 모듈·앱 설치·서버 정보만 남고 저장 줄도 사라진다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => []) });
    mountApp(clients, "/settings#modules");
    const nav = await screen.findByRole("navigation", { name: "설정 섹션" });
    await waitFor(() => expect(within(nav).getAllByRole("link").map((a) => a.textContent?.trim())).toEqual(["화면", "앱 설치", "기능 모듈", "서버 정보"]));
    expect(screen.queryByRole("button", { name: "저장" })).toBeNull();
    expect(screen.queryByRole("button", { name: "되돌리기" })).toBeNull();
    expect(screen.getByText("이 서버에는 켜진 기능이 없습니다.")).toBeTruthy();
    // 사이드바 주 메뉴에는 화면이 없고 아래 고정 줄의 설정만 남는다(5.2R.59: 글자 있는 항목)
    const side = screen.getByRole("navigation", { name: "주 메뉴" });
    expect(within(side).getAllByRole("link").map((a) => a.querySelector(".ac-sidebar-label")?.textContent)).toEqual(["설정"]);
  });

  it("설정 문서 기능만 꺼지면 폼 섹션은 사라지고 설정 문서를 부르지 않으며, 사라진 섹션을 가리키는 #usage 해시는 첫 섹션으로 간다", async () => {
    const { clients, rest } = createFakeClients({ listModules: vi.fn(async () => [mod("m-use", "k-one", "active", { web_roles: ["usage"] })]) });
    mountApp(clients, "/settings#usage");
    const nav = await screen.findByRole("navigation", { name: "설정 섹션" });
    await waitFor(() => expect(within(nav).getAllByRole("link").map((a) => a.textContent?.trim())).toEqual(["화면", "앱 설치", "기능 모듈", "서버 정보"]));
    await waitFor(() => expect(window.location.hash).toBe("#appearance"));
    expect(rest["getSettingsVersioned"]).not.toHaveBeenCalled();
  });

  it("문제 모듈이 있으면 섹션 목록의 기능 모듈 항목에 문제 표시가 붙는다", async () => {
    const { clients } = createFakeClients({ listModules: vi.fn(async () => [mod("m-bad", "k-one", "unsatisfied", { web_roles: ["settings"] })]) });
    mountApp(clients, "/settings");
    const nav = await screen.findByRole("navigation", { name: "설정 섹션" });
    const link = await within(nav).findByRole("link", { name: /기능 모듈/ });
    await waitFor(() => expect(within(link).getByRole("img", { name: "문제가 있는 기능 모듈이 있습니다" })).toBeTruthy());
  });
});
