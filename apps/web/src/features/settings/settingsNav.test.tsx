import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { withViewportWidth } from "../../testing/viewport";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { createSafeStorage, type SafeStorage } from "../../app/storage";
import { SETTINGS_SECTIONS, SettingsScreen, type SectionDef } from "./SettingsScreen";
import { NAV_COLLAPSED_KEY } from "./useSettingsNavState";
import { fieldTexts, filterSections } from "./sectionSearch";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "#");
});
const LONG = { timeout: 15_000 };

// 모듈이 선언한 새 섹션(이름은 임의 값 — 앱은 이 섹션을 모른다)
const FAKE: SectionDef = { id: "zz-fake", titleKey: "zz-fake", descriptionKey: "zz-fake", title: "가짜 모듈 설정", description: "임의 모듈이 선언한 섹션", keys: ["zz_fake"], group: "zz-mod", requires: [], searchTerms: ["고유단어"] };
const pages = { settings: () => [{ index: true, element: <SettingsScreen sections={[...SETTINGS_SECTIONS, FAKE]} /> }] };

function mount(path = "/settings#chat", storage?: SafeStorage) {
  return mountApp(createFakeClients().clients, path, { pages, ...(storage ? { storage } : {}) });
}
// 섹션 목록은 모듈 목록을 받은 뒤 채워진다(그 전에는 nav만 있다).
const nav = async () => {
  const n = await screen.findByRole("navigation", { name: "설정 섹션" }, LONG);
  await waitFor(() => expect(n.querySelector("a, option")).not.toBeNull(), LONG);
  return n;
};
const search = () => screen.getByRole("searchbox", { name: "설정 섹션 검색" }) as HTMLInputElement;

const viewport = (narrow: boolean) => {
  window.innerWidth = narrow ? 1024 : 1440;
};
withViewportWidth(1440);

describe("설정 섹션 검색(순수)", () => {
  it("필드 라벨·설명을 스키마에서 모으고 일치하는 섹션만 남긴다", () => {
    const root = { type: "object", properties: { a: { type: "object", properties: { f: { title: "필드라벨", description: "필드 설명" } } } } };
    expect(fieldTexts(root, ["a"])).toEqual(["필드라벨", "필드 설명"]);
    expect(filterSections([{ id: "x", group: "g", texts: ["하나"] }, { id: "y", group: "g", texts: ["둘"] }], " 둘 ").map((s) => s.id)).toEqual(["y"]);
  });
});

describe("설정 섹션 검색·묶음 접기", () => {
  it("검색어로 일치하는 섹션만 남고 빈 묶음은 숨겨지며, 일치 0이면 안내 한 줄", async () => {
    mount();
    const n = await nav();
    expect(within(n).getByRole("button", { name: "시스템" })).toBeTruthy();
    fireEvent.change(search(), { target: { value: "서버 정보" } });
    expect(within(n).getByRole("link", { name: "서버 정보" })).toBeTruthy();
    expect(within(n).queryByRole("link", { name: "채팅" })).toBeNull();
    expect(within(n).queryByRole("button", { name: "자주 쓰는" })).toBeNull();
    fireEvent.change(search(), { target: { value: "없는검색어zzqq" } });
    expect(within(n).getByText("일치하는 섹션 없음")).toBeTruthy();
    expect(within(n).queryAllByRole("link")).toHaveLength(0);
  });

  it("필드 라벨로만 일치하는 섹션도 걸린다", async () => {
    mount();
    const n = await nav();
    const root = (await import("@agent-console/contracts")).getContractSchema("WorkspaceSettings") as Record<string, unknown>;
    const word = fieldTexts(root, ["chat"]).find((t) => t.length >= 2 && !["채팅"].includes(t));
    expect(word).toBeTruthy();
    fireEvent.change(search(), { target: { value: word as string } });
    // 필드 글은 스키마를 받은 뒤에야 색인되므로(부하에서 늦을 수 있다) 일치가 나타날 때까지 기다린다.
    expect(await within(n).findByRole("link", { name: "채팅" }, LONG)).toBeTruthy();
  });

  it("`/`로 검색 칸에 포커스, Esc로 비운다, Enter는 첫 일치 섹션으로 간다", async () => {
    mount();
    await nav();
    fireEvent.keyDown(document.body, { key: "/" });
    await waitFor(() => expect(document.activeElement).toBe(search()));
    fireEvent.change(search(), { target: { value: "서버 정보" } });
    fireEvent.keyDown(search(), { key: "Enter" });
    expect(await screen.findByRole("region", { name: "서버 정보" })).toBeTruthy();
    fireEvent.keyDown(search(), { key: "Escape" });
    expect(search().value).toBe("");
  });

  it("모듈이 선언한 새 섹션이 코드 수정 없이 목록·검색·드롭다운에 나온다(R0)", async () => {
    mount();
    const n = await nav();
    expect(within(n).getByRole("link", { name: "가짜 모듈 설정" })).toBeTruthy();
    fireEvent.change(search(), { target: { value: "고유단어" } });
    expect(within(n).getAllByRole("link").map((a) => a.textContent)).toEqual(["가짜 모듈 설정"]);
    cleanup();
    viewport(true);
    mount();
    await nav();
    const picker = screen.getByRole("combobox", { name: "섹션 이동" }) as HTMLSelectElement;
    expect(within(picker).getByRole("option", { name: "가짜 모듈 설정" })).toBeTruthy();
  });

  it("묶음 접힘은 저장소에 저장되고 다시 그릴 때 복원되며, 현재 섹션의 묶음은 늘 펼쳐 있다", async () => {
    const storage = createSafeStorage(null);
    const mem = new Map<string, string>();
    const store: SafeStorage = { get: (k) => mem.get(k) ?? null, set: (k, v) => void mem.set(k, v), remove: (k) => void mem.delete(k), keys: () => [...mem.keys()] };
    void storage;
    mount("/settings#chat", store);
    const n = await nav();
    // 현재 섹션(채팅)은 "자주 쓰는" 묶음 — 접을 수 없다
    // 묶음·섹션은 모듈 목록을 받은 뒤 채워지므로(부하에서 늦다) 상태 기반으로 기다린다.
    const frequent = await within(n).findByRole("button", { name: /자주 쓰는/ }, LONG);
    fireEvent.click(frequent);
    expect(await within(n).findByRole("link", { name: "채팅" }, LONG)).toBeTruthy();
    expect(mem.get(NAV_COLLAPSED_KEY)).toBeUndefined();
    const defaults = await within(n).findByRole("button", { name: /실행 기본값/ }, LONG);
    expect(defaults.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(defaults);
    expect(defaults.getAttribute("aria-expanded")).toBe("false");
    expect(JSON.parse(mem.get(NAV_COLLAPSED_KEY) as string)).toEqual(["defaults"]);
    expect(within(n).queryByRole("link", { name: "위임" })).toBeNull();
    cleanup();
    mount("/settings#chat", store);
    const again = await nav();
    const againDefaults = await within(again).findByRole("button", { name: /실행 기본값/ }, LONG);
    expect(againDefaults.getAttribute("aria-expanded")).toBe("false");
    // 접힌 묶음의 섹션이 현재 섹션이면 펼쳐진다
    cleanup();
    mount("/settings#delegation", store);
    const third = await nav();
    expect(await within(third).findByRole("link", { name: "위임" }, LONG)).toBeTruthy();
    const thirdDefaults = await within(third).findByRole("button", { name: /실행 기본값/ }, LONG);
    expect(thirdDefaults.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("설정 좁은 폭(1100px 미만) 드롭다운", () => {
  it("목록 대신 드롭다운이 있고 고르면 섹션·URL 해시가 바뀐다", async () => {
    viewport(true);
    mount();
    await nav();
    const picker = screen.getByRole("combobox", { name: "섹션 이동" }) as HTMLSelectElement;
    expect(screen.queryByRole("link", { name: "서버 정보" })).toBeNull();
    await waitFor(() => expect(picker.value).toBe("chat"));
    expect(picker.querySelectorAll("optgroup").length).toBeGreaterThan(1);
    fireEvent.change(picker, { target: { value: "server" } });
    expect(await screen.findByRole("region", { name: "서버 정보" })).toBeTruthy();
    expect(window.location.hash).toBe("#server");
  });

  it("넓은 폭에서는 드롭다운이 없다", async () => {
    viewport(false);
    mount();
    await nav();
    expect(screen.queryByRole("combobox", { name: "섹션 이동" })).toBeNull();
  });
});
