import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SchemaForm, type FormError } from "@agent-console/schema-form";
import type { ModuleInfo } from "@agent-console/contracts";
import type { WikiChange, WikiSummary } from "@agent-console/contracts/wiki";
import { ToastProvider } from "@agent-console/ui";
import { ApiProvider } from "../../app/ApiContext";
import { CurrentProjectContext } from "../../app/projectScope";
import { createAppQueryClient } from "../../app/queries";
import { ModulesProvider } from "../../modules";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";
import { RunWikiChanges, changeCountText } from "./RunWikiChanges";
import { WikiRefWidget } from "./WikiRefWidget";
import { titleFromContent, usePromoteToWiki, type PromoteSource } from "./usePromoteToWiki";
import { wikiPagePath, wikiPath } from "./wikiPaths";
import { wikiSummary } from "./wikiTestSetup";

afterEach(cleanup);
vi.setConfig({ testTimeout: 40_000 });
const LONG = { timeout: 15_000 };

// 위키 id·이름·경로·동작·역할 이름은 모두 이 테스트 안의 임의 값이다. 화면 코드는 이 이름을 모른다.
const mod = (roles: string[]): ModuleInfo => ({ id: "m-any", kind: "k", version: "1", status: "active", web_roles: roles });
const W = (id: string, name = ""): WikiSummary => wikiSummary({ id, name, directory: `.cfg/wikis/${id}` });
const change = (wiki: string, path: string, op: string, over: Partial<WikiChange> = {}): WikiChange => ({ version: 3, op, sha256: "s", bytes: 1, author: { kind: "agent", label: "작성자 에이전트" }, at: 1_700_000_000, wiki, path, ...over }) as WikiChange;

function Where() {
  const l = useLocation();
  return <output data-testid="where">{l.pathname + l.search}</output>;
}

function harness(ui: React.ReactNode, over: { wiki?: Record<string, unknown>; rest?: Record<string, unknown>; at?: string; project?: string | null } = {}) {
  const made = createFakeClients({ listModules: vi.fn(async () => [mod(["wiki"])]), ...over.rest }, {}, {}, over.wiki);
  const out = render(
    <ApiProvider clients={made.clients}>
      <QueryClientProvider client={createAppQueryClient({ retry: false })}>
        <ModulesProvider subscribeSignals={() => () => undefined}>
          <CurrentProjectContext.Provider value={over.project ?? null}>
            <ToastProvider>
              <MemoryRouter initialEntries={[over.at ?? "/"]}>
                {ui}
                <Where />
              </MemoryRouter>
            </ToastProvider>
          </CurrentProjectContext.Provider>
        </ModulesProvider>
      </QueryClientProvider>
    </ApiProvider>,
  );
  return { ...made, ...out };
}

describe("wiki-ref 위젯", () => {
  const props = { id: "w", label: "위키", required: true, disabled: false, readonly: false, onBlur: () => undefined, schema: {}, options: {}, errors: [] as string[] };

  it("프로젝트 사본(?prj=)이면 그 프로젝트의 위키 목록이 제안이고, 입력은 문자열 값이 된다", async () => {
    const onChange = vi.fn();
    const { wikiClient, clients } = harness(<WikiRefWidget {...props} value="a1" onChange={onChange} />, { at: "/resources/r1?prj=p9", wiki: { listWikis: vi.fn(async () => [W("a1", "첫째"), W("b2")]) } });
    await waitFor(() => expect(document.querySelectorAll("datalist option").length).toBe(2), LONG);
    expect(clients.wiki).toHaveBeenCalledWith("p9");
    expect(Array.from(document.querySelectorAll("datalist option")).map((o) => o.getAttribute("value"))).toEqual(["a1", "b2"]);
    expect(wikiClient.listWikis).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/위키는 프로젝트에 있습니다/)).toBeNull();
    fireEvent.change(screen.getByRole("combobox", { name: "위키" }), { target: { value: "zz" } });
    expect(onChange).toHaveBeenCalledWith("zz");
  });

  it("공용 리소스(주소에 ?prj= 없음)는 직접 입력 + 안내이고, 현재 프로젝트가 있으면 그 위키를 제안한다. 필수가 아니면 비우기 = null", async () => {
    const onChange = vi.fn();
    const { clients } = harness(<WikiRefWidget {...props} required={false} value="a1" onChange={onChange} />, { project: "p1", wiki: { listWikis: vi.fn(async () => [W("a1")]) } });
    expect(await screen.findByText(/위키는 프로젝트에 있습니다. 위키 id가 가져간 프로젝트의 위키 id와 같아야 합니다./, {}, LONG)).toBeTruthy();
    await waitFor(() => expect(document.querySelectorAll("datalist option").length).toBe(1), LONG);
    expect(clients.wiki).toHaveBeenCalledWith("p1");
    fireEvent.change(screen.getByRole("combobox", { name: "위키" }), { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("프로젝트가 없으면 목록을 부르지 않고, 목록 읽기가 실패하면 직접 입력 안내만 보인다", async () => {
    const a = harness(<WikiRefWidget {...props} value="" onChange={() => undefined} />);
    expect(await screen.findByRole("textbox", { name: "위키" })).toBeTruthy();
    expect(a.wikiClient.listWikis).not.toHaveBeenCalled();
    cleanup();
    harness(<WikiRefWidget {...props} value="" onChange={() => undefined} />, { at: "/?prj=p1", wiki: { listWikis: vi.fn(async () => { throw new Error("실패"); }) } });
    expect(await screen.findByText("위키 목록을 불러오지 못해 id를 직접 입력합니다.", {}, LONG)).toBeTruthy();
  });

  it("스키마 폼에 위젯 이름으로 꽂히고, 모르는 위키 경고는 서버 이슈 문장 그대로 보인다(웹이 판단하지 않음)", async () => {
    const schema = { type: "object", properties: { wiki: { type: "string", title: "위키", "x-ui": { widget: "wiki-ref" } } } };
    const widgets = { "wiki-ref": WikiRefWidget };
    const ui = { wiki: { "ui:widget": "wiki-ref" } };
    const errors: FormError[] = [{ path: "/wiki", message: "이 프로젝트에 ‘zz’ 위키가 없습니다 (서버 문장)", severity: "warning" }];
    harness(<SchemaForm schema={schema} uiSchema={ui} customWidgets={widgets} value={{ wiki: "zz" }} onChange={() => undefined} errors={errors} />, { at: "/?prj=p1", wiki: { listWikis: vi.fn(async () => [W("a1")]) } });
    expect(await screen.findByRole("combobox", { name: /위키/ }, LONG)).toBeTruthy();
    expect(await screen.findByText(/서버 문장/, {}, LONG)).toBeTruthy();
  });
});

describe("실행 상세 '고친 위키 페이지 N' 칩", () => {
  it("위키를 가로지르는 변경 한 번(author_run)을 합쳐 한 칩으로 세고, 팝오버 행은 해당 버전 비교 링크다. 지운 페이지는 위키 링크 + 설명", async () => {
    const items = [change("a1", "n/one", "update", { version: 4 }), change("b2", "n/two", "create"), change("a1", "n/gone", "delete")];
    const listSpaceWikiChanges = vi.fn(async () => ({ items, next_cursor: null }));
    const { clients } = harness(<RunWikiChanges runId="run-1" projectId="p1" active={false} />, { wiki: { listSpaceWikiChanges, listWikis: vi.fn(async () => [W("a1", "첫 위키"), W("b2", "둘째 위키")]) } });
    const chip = await screen.findByRole("button", { name: "고친 위키 페이지 3" }, LONG);
    expect(listSpaceWikiChanges).toHaveBeenCalledTimes(1);
    expect(listSpaceWikiChanges).toHaveBeenCalledWith({ authorRun: "run-1", limit: 100 });
    expect(clients.wiki).toHaveBeenCalledWith("p1");
    fireEvent.click(chip);
    const links = await within(await screen.findByRole("dialog", { name: "이 실행이 고친 위키 페이지" }, LONG)).findAllByRole("link");
    const hrefs = links.map((a) => a.getAttribute("href"));
    expect(hrefs).toContain(wikiPagePath("a1", "n/one", { tab: "page", v: 4 }));
    expect(hrefs).toContain(wikiPagePath("b2", "n/two", { tab: "page", v: 3 }));
    expect(hrefs).toContain(wikiPath("a1"));
    expect(screen.getByTitle("지워진 페이지 — 기록에서 되돌릴 수 있습니다")).toBeTruthy();
  });

  it("변경이 0건이거나 읽지 못하면 칩 자체가 없다. 100건 이상은 '100+'", async () => {
    harness(<RunWikiChanges runId="run-1" projectId={null} active={false} />, { wiki: { listSpaceWikiChanges: vi.fn(async () => ({ items: [], next_cursor: null })) } });
    await waitFor(() => expect(screen.queryByRole("button")).toBeNull());
    cleanup();
    const failing = harness(<RunWikiChanges runId="run-1" projectId={null} active={false} />, { wiki: { listSpaceWikiChanges: vi.fn(async () => { throw new Error("꺼짐"); }) } });
    await waitFor(() => expect(failing.wikiClient.listSpaceWikiChanges).toHaveBeenCalled());
    expect(screen.queryByRole("button")).toBeNull();
    expect(changeCountText(99, false)).toBe("99");
    expect(changeCountText(100, false)).toBe("100+");
    expect(changeCountText(3, true)).toBe("100+");
  });

  it("실행 중이면 위키 변경 알림이 오면 다시 센다(1초 디바운스)", async () => {
    const listSpaceWikiChanges = vi.fn(async () => ({ items: [change("a1", "n/one", "create")], next_cursor: null }));
    const { ws } = harness(<RunWikiChanges runId="run-1" projectId={null} active />, { wiki: { listSpaceWikiChanges, listWikis: vi.fn(async () => []) } });
    await screen.findByRole("button", { name: "고친 위키 페이지 1" }, LONG);
    act(() => ws.emitWiki({ wiki_id: "a1", paths: ["n/one"] }));
    await waitFor(() => expect(listSpaceWikiChanges).toHaveBeenCalledTimes(2), LONG);
  });
});

describe("메모리 [위키에 올리기…] (usePromoteToWiki)", () => {
  const SOURCE: PromoteSource = { title: "첫 줄 제목", content: "첫 줄 제목\n둘째 줄" };
  function Host({ load }: { load: () => Promise<PromoteSource | null> }) {
    const p = usePromoteToWiki();
    const item = p.menuItem("promote", load);
    return (
      <>
        {item === null ? <span>줄 없음</span> : <button type="button" disabled={item.disabled} title={item.title} onClick={item.onSelect}>{item.label}</button>}
        {p.dialog}
      </>
    );
  }
  const setup = (roles: string[], project: string | null, wikis: WikiSummary[], load = vi.fn(async () => SOURCE)) => {
    const putWikiPage = vi.fn(async (_w: string, path: string) => ({ value: { page: { path } }, version_hash: "h" }));
    const out = harness(<Host load={load} />, { project, rest: { listModules: vi.fn(async () => [mod(roles)]) }, wiki: { listWikis: vi.fn(async () => wikis), listWikiPages: vi.fn(async () => ({ items: [], truncated: false })), listWikiTemplates: vi.fn(async () => []), putWikiPage, getWikiInfo: vi.fn(async () => ({ pages_root: ".cfg/wikis" })) } });
    return { ...out, load, putWikiPage };
  };

  it("제목은 본문 첫 줄(빈 줄 건너뜀, 80자)이다", () => {
    expect(titleFromContent("\n\n  첫 줄  \n둘째")).toBe("첫 줄");
    expect(Array.from(titleFromContent("가".repeat(200))).length).toBe(80);
    expect(titleFromContent("")).toBe("");
  });

  it("위키 역할이 없거나 현재 프로젝트가 없으면 줄 자체가 없고 위키 목록도 부르지 않는다", async () => {
    const a = setup(["other"], "p1", [W("a1")]);
    await waitFor(() => expect(a.rest.listModules).toHaveBeenCalled());
    await act(async () => undefined);
    expect(screen.getByText("줄 없음")).toBeTruthy();
    expect(a.wikiClient.listWikis).not.toHaveBeenCalled();
    cleanup();
    const b = setup(["wiki"], null, [W("a1")]);
    await waitFor(() => expect(b.rest.listModules).toHaveBeenCalled());
    await act(async () => undefined);
    expect(screen.getByText("줄 없음")).toBeTruthy();
    expect(b.wikiClient.listWikis).not.toHaveBeenCalled();
  });

  it("프로젝트에 위키가 0개면 줄은 보이되 비활성이고 이유가 툴팁에 있다", async () => {
    setup(["wiki"], "p1", []);
    const btn = (await screen.findByRole("button", { name: "위키에 올리기…" }, LONG)) as HTMLButtonElement;
    await waitFor(() => expect(btn.disabled).toBe(true), LONG);
    expect(btn.title).toContain("이 프로젝트에 위키가 없습니다");
  });

  it("누르면 항목을 읽어 새 페이지 대화상자에 제목·본문을 채우고(복사본 안내), 만들면 createOnly로 쓰고 토스트로 알린다. 마지막 위키를 기억한다", async () => {
    const { putWikiPage, load } = setup(["wiki"], "p1", [W("a1", "첫 위키"), W("b2", "둘째 위키")]);
    fireEvent.click(await screen.findByRole("button", { name: "위키에 올리기…" }, LONG));
    expect(await screen.findByText("메모리 항목의 복사본으로 만듭니다. 메모리 항목과 연결되지 않습니다.", {}, LONG)).toBeTruthy();
    expect(load).toHaveBeenCalledTimes(1);
    const dialog = screen.getByRole("dialog");
    expect((within(dialog).getByRole("combobox", { name: /올릴 위키/ }) as HTMLSelectElement).value).toBe("a1");
    fireEvent.change(within(dialog).getByRole("combobox", { name: /올릴 위키/ }), { target: { value: "b2" } });
    await waitFor(() => expect((within(screen.getByRole("dialog")).getByRole("combobox", { name: /올릴 위키/ }) as HTMLSelectElement).value).toBe("b2"));
    const title = within(screen.getByRole("dialog")).getByDisplayValue("첫 줄 제목");
    expect(title).toBeTruthy();
    const path = within(screen.getByRole("dialog")).getByRole("combobox", { name: /경로/ });
    fireEvent.change(path, { target: { value: "notes/from-memory" } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(putWikiPage).toHaveBeenCalledWith("b2", "notes/from-memory", { content: SOURCE.content }, { createOnly: true }), LONG);
    expect(await screen.findByText("위키 페이지를 만들었습니다", {}, LONG)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "열기" }));
    await waitFor(() => expect(screen.getByTestId("where").textContent).toContain("/wiki/b2"), LONG);
  });
});

describe("메모리 화면 항목 메뉴", () => {
  it("역할 memory와 wiki가 둘 다 있고 프로젝트가 있으면 상세 ⋯ 메뉴에 올리기 줄이 있고, 올린 뒤에도 메모리 항목은 쓰지 않는다", async () => {
    const entry = { id: "e1", scope: { kind: "desk", id: "g1" }, key: "k-one", version: 1, bytes: 3, sha256: "s", created_at: 1, created_by: { kind: "user" }, updated_at: 1, updated_by: { kind: "user" }, content: "본문 첫 줄\n둘째" };
    const { clients, rest, wikiClient } = createFakeClients(
      {
        listModules: vi.fn(async () => [mod(["memory", "wiki", "projects"])]),
        listProjects: vi.fn(async () => [{ project: { id: "p1", name: "P1", folder: "/w/p1" }, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg" }]),
        listMemoryScopeKinds: vi.fn(async () => ({ kinds: [{ kind: "desk", label: "책상", id: "{/x}", origin: "user", context_fields: [] }], include_defaults: false })),
        listMemoryScopes: vi.fn(async () => [{ scope: { kind: "desk", id: "g1" }, entries: 1, kind_known: true }]),
        listMemoryEntries: vi.fn(async () => ({ items: [{ ...entry, content: undefined }], next_cursor: null, total: 1 })),
        listMemoryTags: vi.fn(async () => ({ tags: [], truncated: false })),
        getMemoryEntry: vi.fn(async () => entry),
        getModuleOptions: vi.fn(async () => ({ module_id: "m-any", values: { max_entry_bytes: 65_536 } })),
      },
      {},
      {},
      { listWikis: vi.fn(async () => [W("a1", "첫 위키")]), listWikiPages: vi.fn(async () => ({ items: [], truncated: false })), listWikiTemplates: vi.fn(async () => []), getWikiInfo: vi.fn(async () => ({ pages_root: ".cfg/wikis" })) },
    );
    mountApp(clients, "/memory?prj=p1&entry=e1");
    fireEvent.click(within(await screen.findByRole("region", { name: "k-one" }, LONG)).getByRole("button", { name: "더 보기" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "위키에 올리기…" }, LONG));
    expect(await screen.findByText("메모리 항목의 복사본으로 만듭니다. 메모리 항목과 연결되지 않습니다.", {}, LONG)).toBeTruthy();
    expect(within(screen.getByRole("dialog")).getByDisplayValue("본문 첫 줄")).toBeTruthy();
    expect(wikiClient.putWikiPage).not.toHaveBeenCalled();
    const writes = Object.entries(rest).filter(([k]) => /^(put|create|update|delete|patch|move|archive|restore|purge)Memory/.test(k));
    for (const [, fn] of writes) expect(fn).not.toHaveBeenCalled();
  });
});
