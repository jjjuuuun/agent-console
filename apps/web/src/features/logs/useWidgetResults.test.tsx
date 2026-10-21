import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { LogAggregateRow, LogWidget } from "@agent-console/contracts";
import { builtinWidgets, createWidgetRegistry } from "@agent-console/log-view";
import { ApiProvider } from "../../app/ApiContext";
import { createFakeClients } from "../../testing/fakes";
import { LOGS_LIMITS } from "./logsConfig";
import { useWidgetResults } from "./useWidgetResults";

// 대시보드 집계 훅(5R.21 단위 테스트): 보이는 위젯만, 같은 질의는 한 번, 동시 4개 이하, 모르는 종류는 요청하지 않음, 새로 고침 중 이전 본문 유지.
const REGISTRY = createWidgetRegistry(builtinWidgets);
const KIND = builtinWidgets[0]!.kind;
const widget = (id: string, metric: string, kind = KIND, group: string[] = ["dim-a"]): LogWidget => ({ id, kind, query: { group_by: group, metric }, options: {} }) as LogWidget;
const rowsOf = (n: number): LogAggregateRow[] => [{ key: { "dim-a": `v${n}` }, value: n } as unknown as LogAggregateRow];

function setup(aggregate: (body: unknown) => Promise<LogAggregateRow[]>, initial: { widgets: readonly LogWidget[]; paused?: boolean }) {
  const { clients } = createFakeClients({ aggregateLogs: aggregate });
  const wrapper = ({ children }: { children: ReactNode }) => <ApiProvider clients={clients}>{children}</ApiProvider>;
  return renderHook((p: { widgets: readonly LogWidget[]; paused?: boolean }) => useWidgetResults({ widgets: p.widgets, registry: REGISTRY, window: null, tz: "UTC", ...(p.paused === undefined ? {} : { paused: p.paused }) }), { wrapper, initialProps: initial });
}

describe("useWidgetResults", () => {
  it("화면에 보이기 전에는 요청하지 않고, 보이면 요청한 뒤 결과를 돌려준다", async () => {
    const aggregate = vi.fn(async () => rowsOf(1));
    const { result } = setup(aggregate, { widgets: [widget("w1", "m1")] });
    expect(aggregate).not.toHaveBeenCalled();
    expect(result.current.results["w1"]).toEqual({ loading: true });
    act(() => result.current.onVisible("w1"));
    await waitFor(() => expect(result.current.results["w1"]?.rows).toEqual(rowsOf(1)));
    expect(result.current.results["w1"]?.loading).toBe(false);
    expect(aggregate).toHaveBeenCalledTimes(1);
  });

  it("같은 질의의 위젯은 한 번만 요청해 결과를 나눈다", async () => {
    const aggregate = vi.fn(async () => rowsOf(2));
    const { result } = setup(aggregate, { widgets: [widget("a", "same"), widget("b", "same")] });
    act(() => {
      result.current.onVisible("a");
      result.current.onVisible("b");
    });
    await waitFor(() => expect(result.current.results["b"]?.rows).toBeDefined());
    expect(aggregate).toHaveBeenCalledTimes(1);
    expect(result.current.results["a"]?.rows).toEqual(result.current.results["b"]?.rows);
  });

  it("레지스트리에 없는 종류는 요청하지 않고 결과 항목도 만들지 않는다", async () => {
    const aggregate = vi.fn(async () => rowsOf(1));
    const { result } = setup(aggregate, { widgets: [widget("x", "m", "kind-unknown-zz")] });
    act(() => result.current.onVisible("x"));
    await new Promise((r) => setTimeout(r, 30));
    expect(aggregate).not.toHaveBeenCalled();
    expect(result.current.results).toEqual({});
  });

  it("동시 요청은 maxConcurrentAggregates 이하이고 끝나는 대로 다음 요청을 보낸다", async () => {
    let running = 0;
    let peak = 0;
    const gates: Array<() => void> = [];
    const aggregate = vi.fn(
      () =>
        new Promise<LogAggregateRow[]>((resolve) => {
          running += 1;
          peak = Math.max(peak, running);
          gates.push(() => {
            running -= 1;
            resolve(rowsOf(1));
          });
        }),
    );
    const total = LOGS_LIMITS.maxConcurrentAggregates + 3;
    const widgets = Array.from({ length: total }, (_, i) => widget(`w${i}`, `m${i}`));
    const { result } = setup(aggregate, { widgets });
    act(() => widgets.forEach((w) => result.current.onVisible(w.id)));
    await waitFor(() => expect(aggregate).toHaveBeenCalledTimes(LOGS_LIMITS.maxConcurrentAggregates));
    expect(peak).toBe(LOGS_LIMITS.maxConcurrentAggregates);
    await act(async () => gates.shift()?.());
    await waitFor(() => expect(aggregate).toHaveBeenCalledTimes(LOGS_LIMITS.maxConcurrentAggregates + 1));
    expect(peak).toBe(LOGS_LIMITS.maxConcurrentAggregates);
    while (gates.length > 0) await act(async () => gates.shift()?.());
    await waitFor(() => expect(aggregate).toHaveBeenCalledTimes(total));
  });

  it("오류는 위젯 결과의 error로 담기고 ApiError는 code·status를 상세에 싣는다", async () => {
    const aggregate = vi.fn(async () => {
      throw new ApiError(422, { code: "bad_query", message: "질의 오류" });
    });
    const { result } = setup(aggregate, { widgets: [widget("w1", "m1")] });
    act(() => result.current.onVisible("w1"));
    await waitFor(() => expect(result.current.results["w1"]?.error).toBeDefined());
    expect(result.current.results["w1"]?.error).toMatchObject({ message: "질의 오류", code: "bad_query" });
    expect(result.current.results["w1"]?.error?.detail).toContain("status: 422");
  });

  it("새로 고침 중에도 이전 본문을 유지한다(loading=true + rows)", async () => {
    let n = 0;
    let release: () => void = () => undefined;
    const aggregate = vi.fn(async () => {
      n += 1;
      if (n === 2) await new Promise<void>((r) => (release = r));
      return rowsOf(n);
    });
    const { result } = setup(aggregate, { widgets: [widget("w1", "m1")] });
    act(() => result.current.onVisible("w1"));
    await waitFor(() => expect(result.current.results["w1"]?.rows).toEqual(rowsOf(1)));
    act(() => result.current.refresh("w1"));
    await waitFor(() => expect(result.current.results["w1"]?.loading).toBe(true));
    expect(result.current.results["w1"]?.rows).toEqual(rowsOf(1));
    await act(async () => release());
    await waitFor(() => expect(result.current.results["w1"]?.rows).toEqual(rowsOf(2)));
  });

  it("paused면 새 요청을 만들지 않는다", async () => {
    const aggregate = vi.fn(async () => rowsOf(1));
    const { result, rerender } = setup(aggregate, { widgets: [widget("w1", "m1")], paused: true });
    act(() => result.current.onVisible("w1"));
    await new Promise((r) => setTimeout(r, 30));
    expect(aggregate).not.toHaveBeenCalled();
    rerender({ widgets: [widget("w1", "m1")], paused: false });
    await waitFor(() => expect(aggregate).toHaveBeenCalledTimes(1));
  });
});
