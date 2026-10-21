import { QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { createAppQueryClient, isSilentBackgroundError } from "./queries";

/** 데이터가 있는 질의의 갱신이 실패하는 상황을 만든다. 관찰자 옵션과 질의 자체 meta를 따로 줄 수 있다. */
async function failAfterSuccess(opts: { observers: Array<Record<string, unknown> | null>; queryMeta?: Record<string, unknown> }) {
  const onBackgroundError = vi.fn();
  const client = createAppQueryClient({ onBackgroundError, retry: false });
  let fail = false;
  const queryFn = async () => {
    if (fail) throw new Error("boom");
    return 1;
  };
  const key = ["k", Math.random()];
  await client.fetchQuery({ queryKey: key, queryFn, ...(opts.queryMeta ? { meta: opts.queryMeta } : {}) });
  const unsubs = opts.observers.map((meta) => {
    const o = new QueryObserver(client, { queryKey: key, queryFn, staleTime: 0, ...(meta ? { meta } : {}) });
    return o.subscribe(() => {});
  });
  fail = true;
  await client.refetchQueries({ queryKey: key }).catch(() => {});
  unsubs.forEach((u) => u());
  return { onBackgroundError, client, key };
}

describe("백그라운드 오류 토스트 제외 판별", () => {
  it("모든 관찰자가 silentBackgroundError면 토스트를 보내지 않는다", async () => {
    const { onBackgroundError } = await failAfterSuccess({ observers: [{ silentBackgroundError: true }, { silentBackgroundError: true }] });
    expect(onBackgroundError).not.toHaveBeenCalled();
  });
  it("플래그 없는 관찰자가 하나라도 있으면(예: 사용량 화면) 기존대로 토스트를 보낸다", async () => {
    const { onBackgroundError } = await failAfterSuccess({ observers: [{ silentBackgroundError: true }, null] });
    expect(onBackgroundError).toHaveBeenCalledTimes(1);
  });
  it("관찰자가 0개면 제외하지 않는다(빈 every가 true가 되는 함정)", async () => {
    const { onBackgroundError } = await failAfterSuccess({ observers: [] });
    expect(onBackgroundError).toHaveBeenCalledTimes(1);
    expect(isSilentBackgroundError({ observers: [] })).toBe(false);
  });
  it("질의 자체 meta(query.meta)는 관찰자 옵션이 아니므로 제외 근거가 아니다", async () => {
    const { onBackgroundError } = await failAfterSuccess({ observers: [null], queryMeta: { silentBackgroundError: true } });
    expect(onBackgroundError).toHaveBeenCalledTimes(1);
  });
  it("true가 아닌 값(문자열 등)은 플래그로 보지 않는다", () => {
    expect(isSilentBackgroundError({ observers: [{ options: { meta: { silentBackgroundError: "yes" } } }] })).toBe(false);
    expect(isSilentBackgroundError({ observers: [{ options: { meta: { silentBackgroundError: true } } }, { options: {} }] })).toBe(false);
    expect(isSilentBackgroundError({ observers: [{ options: { meta: { silentBackgroundError: true } } }] })).toBe(true);
  });
});
