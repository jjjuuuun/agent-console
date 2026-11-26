import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo } from "@agent-console/contracts";
import { ApiError } from "@agent-console/api-client";
import type { SddInfo, SpecTemplate } from "@agent-console/contracts/sdd";
import { createFakeClients } from "../../testing/fakes";
import { mountApp } from "../../testing/screenHarness";

afterEach(cleanup);

const LONG = { timeout: 15_000 };
const NOW = Math.floor(Date.now() / 1000);
const BASE = "/sdd/templates/t1";
const mod: ModuleInfo = { id: "m-any", kind: "k", version: "0.0.1", status: "active", web_roles: ["sdd", "settings"] };
const INFO = { spec_root: ".cfg/specs", limits: { max_bulk_start: 10 }, capabilities: { runs: true, templates: true, import_export: true, verification: false, automation: false }, writable: true } as SddInfo;
const tpl = { kind: "k-x", id: "t1", name: "임의 틀", documents: [{ id: "d1", title: "문서가", file: "a.md" }], rules: {} } as unknown as SpecTemplate;
const versions = [
  { kind: "k-x", id: "t1", version_hash: "cur00000aaaa", saved_at: NOW - 60, message: "방금" },
  { kind: "k-x", id: "t1", version_hash: "prev1111bbbb", saved_at: NOW - 7200 },
];
const diff = {
  kind: "k-x",
  id: "t1",
  from_hash: "prev1111bbbb",
  to_hash: "cur00000aaaa",
  changes: [{ op: "replace", path: "/name", before: "옛 틀", after: "임의 틀" }],
  content_changes: [{ path: "a.md", op: "replace", before_hash: "x", after_hash: "y" }],
};

function open(rest: Record<string, unknown>) {
  const made = createFakeClients(
    { listModules: vi.fn(async () => [mod]), listDefinitionVersions: vi.fn(async () => versions), listVersionFiles: vi.fn(async () => []), ...rest },
    {
      getSddInfo: vi.fn(async () => INFO),
      listSpecs: vi.fn(async () => []),
      listSpecTemplates: vi.fn(async () => [{ id: "t1", name: "임의 틀", documents: [], run_profiles: [] }]),
      getSpecTemplate: vi.fn(async () => ({ value: tpl, version_hash: "cur00000aaaa" })),
      listSpecTemplateFiles: vi.fn(async () => []),
    },
  );
  mountApp(made.clients, "/spec-templates?template=t1&tab=versions");
  return made;
}

describe("문서 틀 버전 비교", () => {
  it("비교를 준다: 변경 표와 본문 변경 행이 보이고 안내 문구는 없다", async () => {
    const { rest } = open({ diffDefinitionVersions: vi.fn(async () => diff) });
    expect(await screen.findByRole("table", { name: "필드 변경 표" }, LONG)).toBeTruthy();
    expect(rest.diffDefinitionVersions).toHaveBeenCalledWith(BASE, "cur00000aaaa", undefined);
    expect(rest.diffDefinitionVersions).toHaveBeenCalledWith(BASE, "prev1111bbbb", undefined);
    expect(screen.getByText("a.md")).toBeTruthy();
    expect(screen.queryByTestId("sdd-template-compare-off")).toBeNull();
  });

  it("비교 경로가 404(옛 서버): 비교 칸 없이 안내만, 목록은 그대로", async () => {
    open({ diffDefinitionVersions: vi.fn(async () => Promise.reject(new ApiError(404, { code: "not_found", message: "Not Found" } as never))) });
    expect(await screen.findByTestId("sdd-template-compare-off", {}, LONG)).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("region", { name: "버전 비교" })).toBeNull());
    expect(screen.getByRole("list", { name: "버전 목록" })).toBeTruthy();
  });
});
