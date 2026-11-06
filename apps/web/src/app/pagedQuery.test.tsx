import { cleanup, renderHook, waitFor, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiProvider } from "./ApiContext";
import { flatten, useApiPagedQuery, type CursorPage } from "./pagedQuery";
import { createAppQueryClient } from "./queries";
import { createFakeClients } from "../testing/fakes";

afterEach(cleanup);

type Item = { id: string };
const page = (ids: string[], next: string | null, source = "project"): CursorPage<Item> => ({ items: ids.map((id) => ({ id })), next_cursor: next, source });

describe("flatten", () => {
  it("페이지를 이어 붙이고 같은 id는 앞의 것만 남긴다", () => {
    const out = flatten([page(["a", "b"], "c1"), page(["b", "c"], null)]);
    expect(out.items?.map((i) => i.id)).toEqual(["a", "b", "c"]);
  });
  it("출처가 바뀌는 페이지의 첫 항목에 구분 자리를 만든다(빈 페이지는 만들지 않는다)", () => {
    const out = flatten([page(["a"], "x"), page([], "y", "app"), page(["z"], null, "app")]);
    expect([...out.breaks]).toEqual([["z", "app"]]);
    expect(out.sources.get("a")).toBe("project");
    expect(out.sources.get("z")).toBe("app");
  });
  it("페이지가 아직 없으면 undefined", () => {
    expect(flatten(undefined).items).toBeUndefined();
  });
});

function wrapperFor(clients: ReturnType<typeof createFakeClients>["clients"]) {
  const queryClient = createAppQueryClient({ retry: false });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ApiProvider clients={clients}>{children}</ApiProvider>
    </QueryClientProvider>
  );
}

describe("useApiPagedQuery", () => {
  it("[더 불러오기]는 커서를 그대로 넘겨 다음 페이지를 이어 붙인다", async () => {
    const { clients } = createFakeClients();
    const load = vi.fn(async (_rest: unknown, cursor: string | null) => (cursor === null ? page(["a", "b"], "opaque.1") : page(["c"], null)));
    const { result } = renderHook(() => useApiPagedQuery<Item>(["list", "t"], load), { wrapper: wrapperFor(clients) });
    await waitFor(() => expect(result.current.items?.map((i) => i.id)).toEqual(["a", "b"]));
    expect(result.current.hasMore).toBe(true);
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items?.map((i) => i.id)).toEqual(["a", "b", "c"]));
    expect(load.mock.calls.map((c) => c[1])).toEqual([null, "opaque.1"]);
    expect(result.current.hasMore).toBe(false);
  });

  it("키(거르기 조건)가 바뀌면 첫 페이지부터 다시 읽는다", async () => {
    const { clients } = createFakeClients();
    const load = vi.fn(async (_rest: unknown, cursor: string | null) => (cursor === null ? page(["a"], "k1") : page(["b"], null)));
    let scope = "p1";
    const { result, rerender } = renderHook(() => useApiPagedQuery<Item>(["list", "t", scope], load), { wrapper: wrapperFor(clients) });
    await waitFor(() => expect(result.current.items?.length).toBe(1));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items?.length).toBe(2));
    scope = "p2";
    rerender();
    await waitFor(() => expect(result.current.items?.map((i) => i.id)).toEqual(["a"]));
    expect(load.mock.calls.map((c) => c[1])).toEqual([null, "k1", null]);
  });
});
