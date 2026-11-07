import { cleanup, render, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { GraphSummary } from "@agent-console/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { createFakeClients } from "../../testing/fakes";
import { GraphIssuesPreview } from "./GraphIssuesPreview";

afterEach(cleanup);

const graph = { id: "g1", name: "팀", version_hash: "h1", node_count: 1, edge_count: 0, entry_labels: [] } as unknown as GraphSummary;

function mount(project?: string | null) {
  const { clients } = createFakeClients();
  const validateGraph = vi.fn(async () => []);
  (clients.rest as unknown as Record<string, unknown>)["validateGraph"] = validateGraph;
  render(
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>
        <GraphIssuesPreview graph={graph} project={project} />
      </ApiProvider>
    </QueryClientProvider>,
  );
  return validateGraph;
}

describe("GraphIssuesPreview", () => {
  it("project가 있으면 검증 호출에 그대로 넘긴다", async () => {
    const validate = mount("p1");
    await waitFor(() => expect(validate).toHaveBeenCalledWith("g1", undefined, { project: "p1" }));
  });
  it("project가 없으면 옵션 값이 비어 있다(하위 호환)", async () => {
    const validate = mount();
    await waitFor(() => expect(validate).toHaveBeenCalledWith("g1", undefined, { project: undefined }));
  });
});
