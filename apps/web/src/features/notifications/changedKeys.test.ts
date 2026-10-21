import { describe, expect, it } from "vitest";
import { changedKeysOnly } from "../settings";
describe("changedKeysOnly", () => {
  const shown = { enabled: false, sound: false, events: ["interaction.requested"], only_when_hidden: true };
  it("건드리지 않은 기본값은 쓰지 않는다", () => {
    expect(changedKeysOnly(undefined, shown, { ...shown, sound: true })).toEqual({ sound: true });
  });
  it("저장된 키는 기본값과 같아져도 남는다", () => {
    const stored = { sound: true };
    expect(changedKeysOnly(stored, { ...shown, sound: true }, { ...shown, sound: false })).toEqual({ sound: false });
  });
  it("저장된 다른 키(알 수 없는 키 포함)를 보존한다", () => {
    const stored = { events: ["a"], extra: 1 } as never;
    expect(changedKeysOnly(stored, { ...shown, events: ["a"] }, { ...shown, events: ["a"], enabled: true })).toEqual({ events: ["a"], extra: 1, enabled: true });
  });
});
