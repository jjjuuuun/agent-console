import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import type { WorkspaceSettings } from "@agent-console/contracts";
import { saveLanguage } from "./saveLanguage";

const conflict = () =>
  new ApiError(412, { code: "version_conflict", message: "x", details: { current_version_hash: "h2", your_version_hash: "h1" } });

describe("saveLanguage: ui.language 한 칸만 저장", () => {
  it("최신 문서를 읽어 그 칸만 바꾸고 If-Match(읽은 해시)로 쓴다. 다른 필드는 그대로", async () => {
    const doc: WorkspaceSettings = { chat: { x: 1 } as never, ui: { notifications: { sound: true } as never } };
    const put = vi.fn(async (next: WorkspaceSettings) => ({ value: next, version_hash: "h2" }));
    const rest = { getSettingsVersioned: vi.fn(async () => ({ value: doc, version_hash: "h1" })), putSettingsVersioned: put };
    const saved = await saveLanguage(rest, "en");
    expect(put).toHaveBeenCalledWith({ ...doc, ui: { notifications: { sound: true }, language: "en" } }, "h1");
    expect(saved.version_hash).toBe("h2");
  });

  it("자동 = null을 쓴다", async () => {
    const put = vi.fn(async (next: WorkspaceSettings) => ({ value: next, version_hash: "h2" }));
    await saveLanguage({ getSettingsVersioned: async () => ({ value: {}, version_hash: undefined }), putSettingsVersioned: put }, null);
    expect(put).toHaveBeenCalledWith({ ui: { language: null } }, undefined);
  });

  it("412면 한 번 다시 읽고 다시 쓴다", async () => {
    let n = 0;
    const get = vi.fn(async () => {
      n += 1;
      return { value: { agent_defaults: { n } } as never, version_hash: `h${n}` };
    });
    const put = vi.fn(async (next: WorkspaceSettings, hash?: string) => {
      if (hash === "h1") throw conflict();
      return { value: next, version_hash: "h3" };
    });
    await saveLanguage({ getSettingsVersioned: get, putSettingsVersioned: put }, "ko");
    expect(get).toHaveBeenCalledTimes(2);
    expect(put).toHaveBeenLastCalledWith({ agent_defaults: { n: 2 }, ui: { language: "ko" } }, "h2");
  });

  it("두 번째도 412면 던진다. 다른 오류는 다시 시도하지 않는다", async () => {
    const get = vi.fn(async () => ({ value: {}, version_hash: "h" }));
    await expect(saveLanguage({ getSettingsVersioned: get, putSettingsVersioned: async () => { throw conflict(); } }, "ko")).rejects.toBeInstanceOf(ApiError);
    expect(get).toHaveBeenCalledTimes(2);
    const get2 = vi.fn(async () => ({ value: {}, version_hash: "h" }));
    await expect(saveLanguage({ getSettingsVersioned: get2, putSettingsVersioned: async () => { throw new ApiError(500, { code: "x", message: "y" }); } }, "ko")).rejects.toBeInstanceOf(ApiError);
    expect(get2).toHaveBeenCalledTimes(1);
  });
});
