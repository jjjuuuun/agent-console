import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CopyItem, CopyKindInfo } from "@agent-console/contracts/projects";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { createFakeClients } from "../../testing/fakes";
import { useSpaceItems } from "./useSpaceItems";

afterEach(cleanup);

// 종류 이름은 모두 임의 값이다. 화면 코드는 이 이름을 모른다(서버가 종류 목록과 방향 플래그를 준다).
const KINDS: CopyKindInfo[] = [
  { kind: "zz-made-up", library: true, portable: true },
  { kind: "zz-lib-only", library: true, portable: false },
  { kind: "zz-proj-only", library: false, portable: true },
];
const ITEMS: Record<string, CopyItem[]> = {
  "zz-made-up": [{ kind: "zz-made-up", id: "i1", name: "임의 항목", description: "설명" }],
  "zz-lib-only": [{ kind: "zz-lib-only", id: "i2", name: "" }],
  "zz-proj-only": [{ kind: "zz-proj-only", id: "i3", name: "프로젝트 항목" }],
};

function setup() {
  const made = createFakeClients({
    listCopyKinds: vi.fn(async () => KINDS),
    listCopyItems: vi.fn(async (_space: string | null, kind?: string) => ITEMS[kind ?? ""] ?? []),
  });
  const queryClient = createAppQueryClient({ retry: false });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ApiProvider clients={made.clients}>{children}</ApiProvider>
    </QueryClientProvider>
  );
  return { rest: made.rest as unknown as { listCopyKinds: ReturnType<typeof vi.fn>; listCopyItems: ReturnType<typeof vi.fn> }, wrapper };
}

describe("useSpaceItems: 복사 종류는 서버가 준다", () => {
  it("코드 수정 없이 임의 이름의 종류가 나오고, portable 플래그가 true인 종류만 읽는다", async () => {
    const { rest, wrapper } = setup();
    const { result } = renderHook(() => useSpaceItems(null, "portable", true), { wrapper });
    await waitFor(() => expect(result.current.items.length).toBe(2));
    expect(result.current.items.map((i) => i.kind)).toEqual(["zz-made-up", "zz-proj-only"]);
    // 종류 제목은 그 종류를 맡은 화면이 없으면 서버가 준 종류 이름 원문이다
    expect(result.current.items[0]?.kindTitle).toBe("zz-made-up");
    expect(rest.listCopyKinds).toHaveBeenCalledWith(null);
    expect(rest.listCopyItems).not.toHaveBeenCalledWith(null, "zz-lib-only");
  });

  it("library 플래그면 공용에 둘 수 있는 종류만, 이름이 비면 id를 이름으로 쓰고 공간 id를 그대로 넘긴다", async () => {
    const { rest, wrapper } = setup();
    const { result } = renderHook(() => useSpaceItems("p1", "library", true), { wrapper });
    await waitFor(() => expect(result.current.items.length).toBe(2));
    expect(result.current.items.map((i) => [i.kind, i.name])).toEqual([["zz-made-up", "임의 항목"], ["zz-lib-only", "i2"]]);
    expect(rest.listCopyKinds).toHaveBeenCalledWith("p1");
    expect(result.current.failed).toBe(false);
  });

  it("enabled=false면 읽지 않고, 종류 목록을 못 읽으면 failed", async () => {
    const { rest, wrapper } = setup();
    const off = renderHook(() => useSpaceItems(null, "portable", false), { wrapper });
    expect(off.result.current.loading).toBe(false);
    expect(rest.listCopyKinds).not.toHaveBeenCalled();
    cleanup();
    const made = createFakeClients({ listCopyKinds: vi.fn(async () => { throw new Error("실패"); }) });
    const queryClient = createAppQueryClient({ retry: false });
    const wrapper2 = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}><ApiProvider clients={made.clients}>{children}</ApiProvider></QueryClientProvider>
    );
    const bad = renderHook(() => useSpaceItems(null, "portable", true), { wrapper: wrapper2 });
    await waitFor(() => expect(bad.result.current.failed).toBe(true));
    expect(bad.result.current.items).toEqual([]);
  });
});
