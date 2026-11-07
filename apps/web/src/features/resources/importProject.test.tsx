import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider } from "../../app/ApiContext";
import { CurrentProjectContext } from "../../app/projectScope";
import { createAppQueryClient } from "../../app/queries";
import { createFakeClients } from "../../testing/fakes";
import { resourceTypes } from "../../testing/teamFixtures";
import { ImportDialog } from "./ImportDialog";

afterEach(cleanup);

const sources = [{ id: "src-a", title: "출처 에이", description: "", path: "/p/.x", available: true }];
const candidates = [{ id: "c1", path: "a.md", kind: "resource", resource_type: "rt-doc", name: "지침 가", suggested_id: "a", size: 10, warnings: [] }];

function mount(project: string | null, extra: Record<string, unknown>) {
  const clients = createFakeClients({ listResourceTypes: vi.fn(async () => resourceTypes), ...extra });
  render(
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients.clients}>
        <CurrentProjectContext.Provider value={project}>
          <ImportDialog onClose={() => undefined} onShowImported={() => undefined} />
        </CurrentProjectContext.Provider>
      </ApiProvider>
    </QueryClientProvider>,
  );
}

describe("가져오기: 현재 프로젝트 전달", () => {
  it("출처·미리보기·적용 호출에 ?project= 로 현재 프로젝트를 넘긴다", async () => {
    const listImportSources = vi.fn(async () => sources);
    const previewImport = vi.fn(async () => ({ source: "src-a", root: "/p/.x", candidates }));
    const importResources = vi.fn(async () => ({ source: "src-a", items: [{ source: "src-a", kind: "resource", id: "c1", target_id: "a", action: "created" }] }));
    mount("prj-1", { listImportSources, previewImport, importResources });
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("radio", { name: /출처 에이/ }));
    expect(listImportSources).toHaveBeenCalledWith({ project: "prj-1" });
    fireEvent.click(within(dialog).getByRole("button", { name: "다음" }));
    await waitFor(() => expect(previewImport).toHaveBeenCalledWith({ source: "src-a" }, { project: "prj-1" }));
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: "전체 선택" }));
    fireEvent.click(within(dialog).getByRole("button", { name: /^가져오기/ }));
    await waitFor(() => expect(importResources).toHaveBeenCalledWith(expect.objectContaining({ source: "src-a" }), { project: "prj-1" }));
  });

  it("프로젝트가 없으면 project 없이 부르고 프로젝트 고르기 안내를 덧붙인다", async () => {
    const listImportSources = vi.fn(async () => []);
    mount(null, { listImportSources });
    expect(await screen.findByText(/가져올 수 있는 출처가 없습니다.*프로젝트를 고르세요/)).toBeTruthy();
    expect(listImportSources).toHaveBeenCalledWith(undefined);
  });
});
