/** 스펙 화면 통합 테스트 공용 준비(가짜 클라이언트 + 앱 마운트). 이름은 전부 임의 값이고 화면 코드는 이 이름을 모른다. */
import { vi } from "vitest";
import type { SddClient } from "@agent-console/api-client";
import type { ModuleInfo, Project, ProjectView } from "@agent-console/contracts";
import type { EffectiveSyntax, ParsedTask, SddInfo, SpecSummary, SpecView } from "@agent-console/contracts/sdd";
import type { SafeStorage } from "../../app/storage";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

export const LONG = { timeout: 15_000 };
// 상태·문서·단계 이름은 모두 임의 값이다. 화면 코드는 이 이름을 모른다.
const mod = (roles: string[], extra: Partial<ModuleInfo> = {}): ModuleInfo => ({ id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: roles, ...extra });
const MODULES = async () => [mod(["sdd", "projects", "settings", "runs"])];
export const project = (id: string, over: Partial<Project> = {}): Project => ({ id, name: id.toUpperCase(), folder: `/w/${id}`, ...over }) as Project;
export const projectView = (p: Project, over: Partial<ProjectView> = {}): ProjectView => ({ project: p, status: "ready", config_writable: true, kinds: [], records_writable: true, config_dir: ".cfg", ...over }) as ProjectView;

export const INFO: SddInfo = { spec_root: ".cfg/specs", limits: { max_bulk_start: 10 }, capabilities: { runs: true, templates: true, import_export: true, verification: false, automation: false }, writable: true } as SddInfo;
export const STATUSES = [
  { id: "s-open", label: "열림", tone: "neutral" },
  { id: "s-end", label: "끝남", tone: "success", done: true },
];
export const task = (key: string, status = "s-open", extra: Partial<ParsedTask> = {}): ParsedTask => ({ key, id: key, title: `작업 ${key}`, status, document: "d-tasks", line: 4, line_hash: `h-${key}`, ready: true, ...extra });
export const specView = (over: Partial<SpecView> = {}): SpecView => ({
  spec: { kind: "k-x", id: "sp1", name: "결제", documents: [{ id: "d-req", title: "요구", file: "req.md", roles: ["requirements"], state: "g-draft" }, { id: "d-tasks", title: "작업표", file: "tasks.md", roles: ["tasks"] }], rules: {} },
  index: { tasks: [task("T1"), task("T2", "s-end")], stages: [] },
  version_hash: "v1",
  directory: ".cfg/specs/sp1",
  task_statuses: STATUSES,
  document_states: [{ id: "g-draft", label: "초안", tone: "neutral" }],
  issues: [],
  ...over,
});
export const summary = (over: Partial<SpecSummary> = {}): SpecSummary => ({ id: "sp1", name: "결제", directory: ".cfg/specs/sp1", tasks_total: 2, tasks_done: 1, ready: 1, updated_at: 1_700_000_000, documents: [{ id: "d-req", title: "요구", state: "g-draft", state_label: "초안", tone: "neutral" }], ...over });
export const SYNTAX: EffectiveSyntax = { empty: false, statuses: STATUSES, sources: { "task.list": "default" } } as EffectiveSyntax;

interface Fixture {
  info?: SddInfo;
  specs?: SpecSummary[];
  view?: SpecView;
  syntax?: EffectiveSyntax;
  tasks?: ParsedTask[];
  projects?: ProjectView[];
  modules?: ModuleInfo[];
  sdd?: Record<string, unknown>;
  storage?: SafeStorage;
}

export function setup(path: string, f: Fixture = {}) {
  const view = f.view ?? specView();
  const projects = f.projects ?? [projectView(project("p1", { name: "결제앱" }))];
  const { clients, ws, sddClient, sdd, rest } = createFakeClients(
    { listModules: vi.fn(async () => f.modules ?? (await MODULES())), listProjects: vi.fn(async () => projects) },
    {},
    {
      getSddInfo: vi.fn(async () => f.info ?? INFO),
      listSpecs: vi.fn(async () => f.specs ?? []),
      listSpecTemplates: vi.fn(async () => []),
      getSpec: vi.fn(async () => ({ value: view, version_hash: view.version_hash })),
      listSpecVariables: vi.fn(async () => []),
      getSpecSyntax: vi.fn(async () => f.syntax ?? SYNTAX),
      listSpecTasks: vi.fn(async () => f.tasks ?? view.index?.tasks ?? []),
      getSpecDocument: vi.fn(async (_id: string, doc: string) => ({ value: { document_id: doc, file: "x.md", content: `# ${doc}`, content_hash: "c1", issues: [] }, version_hash: "c1" })),
      ...f.sdd,
    },
  );
  const mounted = mountApp(clients, path, f.storage === undefined ? {} : { storage: f.storage });
  return { ...mounted, clients, ws, sdd: sddClient as unknown as { [K in keyof SddClient]: ReturnType<typeof vi.fn> }, sddFactory: sdd, rest };
}

