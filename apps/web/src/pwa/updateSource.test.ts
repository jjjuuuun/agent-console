import { describe, expect, it, vi } from "vitest";
import { createUpdateSource } from "./updateSource";

function setup(controlled: boolean) {
  let notify: () => void = () => {};
  const apply = vi.fn(async () => {});
  const state = { controlled };
  const source = createUpdateSource({
    register: (hooks) => {
      notify = hooks.onNeedRefresh;
      return apply;
    },
    hasController: () => state.controlled,
  });
  return { source, notify: () => notify(), apply, state };
}

describe("서비스 워커 갱신 알림", () => {
  it("제어하는 워커가 없을 때의 대기(최초 설치)는 갱신으로 알리지 않는다", () => {
    const { source, notify } = setup(false);
    const listener = vi.fn();
    source.subscribe(listener);
    notify();
    expect(source.getSnapshot()).toBe(false);
    expect(listener).not.toHaveBeenCalled();
  });
  it("제어하는 워커가 있으면 갱신으로 알리고 구독자를 깨운다", () => {
    const { source, notify } = setup(true);
    const listener = vi.fn();
    source.subscribe(listener);
    notify();
    expect(source.getSnapshot()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
  });
  it("같은 페이지에서 최초 설치 뒤 워커가 제어권을 얻으면 이후 진짜 갱신은 알린다", () => {
    const { source, notify, state } = setup(false);
    notify();
    expect(source.getSnapshot()).toBe(false);
    state.controlled = true;
    notify();
    expect(source.getSnapshot()).toBe(true);
  });
  it("apply는 등록기의 갱신 함수를 true로 부른다", () => {
    const { source, apply } = setup(true);
    source.apply();
    expect(apply).toHaveBeenCalledWith(true);
  });
});
