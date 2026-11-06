/** 위키 화면 통합 테스트 공용 준비(가짜 클라이언트 + 앱 마운트). 이름·경로·규칙 id·링크 상태는 전부 임의 값이고 화면 코드는 이 이름을 모른다. */
import { vi } from "vitest";
import type { WikiClient } from "@agent-console/api-client";
import type { ModuleInfo, Project, ProjectView } from "@agent-console/contracts";
import type { EffectiveWikiSyntax, WikiInfo, WikiPageList, WikiPageSummary, WikiPageView, WikiSummary, WikiView } from "@agent-console/contracts/wiki";
import type { SafeStorage } from "../../app/storage";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

export const LONG = { timeout: 15_000 };
const mod = (roles: string[], extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles, ...extra });
export const project = (id: string, over: Partial<Project> = {}): Project => ({ id, name: id.toUpperCase(), folder: `/w/${id}`, ...over }) as Project;
export const projectView = (p: Project, over: Partial<ProjectView> = {}): ProjectView => ({ project: p, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg", ...over }) as ProjectView;

export const INFO: WikiInfo = {
  pages_root: ".cfg/wikis",
  capabilities: { history: true, search: true, runs: false, rules_library: false, import_export: true },
  limits: { max_page_bytes: 524288, max_pages: 10000, graph_max_nodes: 300 },
};
export const SYNTAX: EffectiveWikiSyntax = { syntax: { links: [{ id: "r-link", kind: "k-link", pattern: "x", insert: "<<{target}>>" }] }, sources: {}, empty: false };
export const wikiSummary = (over: Partial<WikiSummary> = {}): WikiSummary => ({ id: "w1", name: "노트", description: "설명 글", pages: 2, broken_links: 1, directory: ".cfg/wikis/w1", rules: [], updated_at: 1_700_000_000, ...over });
export const wikiView = (over: Partial<WikiView["wiki"]> = {}, rest: Partial<WikiView> = {}): WikiView => ({
  wiki: { kind: "k-wiki", id: "w1", name: "노트", rules: [], home: null, ...over },
  version_hash: "wv1",
  directory: ".cfg/wikis/w1",
  rules: { rules: [], entries: [] },
  issues: [],
  ...rest,
});
export const pageSummary = (path: string, over: Partial<WikiPageSummary> = {}): WikiPageSummary => ({ path, title: path.split("/").pop()!, tags: [], aliases: [], bytes: 10, updated_at: 1_700_000_000, ...over });
export const pageView = (path: string, content: string, over: Partial<WikiPageView> = {}): WikiPageView => ({
  page: pageSummary(path),
  content,
  content_hash: `h-${content.length}`,
  front_matter: {},
  headings: [],
  links: [],
  backlinks: [],
  issues: [],
  ...over,
});

export interface Fixture {
  info?: WikiInfo;
  wikis?: WikiSummary[];
  view?: WikiView;
  pages?: WikiPageList;
  /** 경로 → 본문(없으면 404) */
  page?: Readonly<Record<string, WikiPageView>>;
  syntax?: EffectiveWikiSyntax;
  projects?: ProjectView[];
  modules?: ModuleInfo[];
  wiki?: Record<string, unknown>;
  storage?: SafeStorage;
}

export function setup(path: string, f: Fixture = {}) {
  const view = f.view ?? wikiView();
  const projects = f.projects ?? [projectView(project("p1", { name: "결제앱" }))];
  const pages = f.pages ?? { items: Object.values(f.page ?? {}).map((p) => p.page), truncated: false };
  const { clients, ws, wikiClient, wiki, rest } = createFakeClients(
    { listModules: vi.fn(async () => f.modules ?? [mod(["wiki", "projects", "settings"])]), listProjects: vi.fn(async () => projects) },
    {},
    {},
    {
      getWikiInfo: vi.fn(async () => f.info ?? INFO),
      listWikis: vi.fn(async () => f.wikis ?? []),
      getWiki: vi.fn(async () => ({ value: view, version_hash: view.version_hash })),
      listWikiPages: vi.fn(async () => pages),
      getWikiPage: vi.fn(async (_w: string, p: string) => {
        const hit = f.page?.[p];
        if (hit === undefined) throw Object.assign(new Error("없음"), { status: 404 });
        return { value: hit, version_hash: hit.content_hash };
      }),
      getWikiSyntax: vi.fn(async () => f.syntax ?? SYNTAX),
      getWikiPageHistory: vi.fn(async () => ({ items: [], pruned: false })),
      listWikiTemplates: vi.fn(async () => []),
      listWikiRules: vi.fn(async () => []),
      previewWikiPage: vi.fn(async (_w: string, p: string, content: string) => ({ page: pageSummary(p), links: [], issues: [], rule_results: [], would_reject: false, content })),
      ...f.wiki,
    },
  );
  const mounted = mountApp(clients, path, f.storage === undefined ? {} : { storage: f.storage });
  return { ...mounted, clients, ws, wiki: wikiClient as unknown as { [K in keyof WikiClient]: ReturnType<typeof vi.fn> }, wikiFactory: wiki, rest };
}
