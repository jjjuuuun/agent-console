import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@agent-console/api-client";
import { ApiProvider } from "../../app/ApiContext";
import { createFakeClients, pendingInteraction } from "../../testing/fakes";
import { useInteractionRespond } from "./useInteractionRespond";

// 채팅 카드·입력창·실행 상세가 함께 쓰는 응답 훅의 오류 경로(409·404·422·오프라인·기타)를 앱 없이 확인한다.
function setup(respond: () => Promise<unknown>) {
  const { clients } = createFakeClients({ respondInteraction: respond });
  const wrapper = ({ children }: { children: ReactNode }) => <ApiProvider clients={clients}>{children}</ApiProvider>;
  const spies = { applyInteraction: vi.fn(), refresh: vi.fn(), notify: vi.fn() };
  const { result } = renderHook(() => useInteractionRespond(spies), { wrapper });
  return { result, spies, target: pendingInteraction("i1") };
}

describe("useInteractionRespond", () => {
  it("성공하면 true, 서버가 준 상태를 반영하고 목록을 새로 읽는다", async () => {
    const answered = { ...pendingInteraction("i1"), status: "answered" };
    const { result, spies, target } = setup(async () => answered);
    let ok = false;
    await act(async () => {
      ok = await result.current.respond(target, { a: 1 });
    });
    expect(ok).toBe(true);
    expect(spies.applyInteraction).toHaveBeenCalledWith(answered);
    expect(spies.refresh).toHaveBeenCalled();
  });

  it("409 interaction_closed: 현재 상태를 반영하고 안내한 뒤 던진다", async () => {
    const current = { ...pendingInteraction("i1"), status: "answered" };
    const { result, spies, target } = setup(async () => {
      throw new ApiError(409, { code: "interaction_closed", message: "닫힘", details: { interaction: current } });
    });
    await act(async () => {
      await expect(result.current.respond(target, {})).rejects.toThrow(/이미 답했거나 닫힌/);
    });
    expect(spies.applyInteraction).toHaveBeenCalledWith(current);
    expect(spies.notify).toHaveBeenCalledTimes(1);
    expect(spies.refresh).toHaveBeenCalled();
  });

  it("404: 안내하고 목록을 새로 읽은 뒤 던진다", async () => {
    const { result, spies, target } = setup(async () => {
      throw new ApiError(404, { code: "not_found", message: "없음" });
    });
    await act(async () => {
      await expect(result.current.respond(target, {})).rejects.toThrow();
    });
    expect(spies.notify).toHaveBeenCalledTimes(1);
    expect(spies.refresh).toHaveBeenCalled();
  });

  it("422: 필드 오류로 매핑되면 false를 돌려주고 errorsOf로 읽으며, 다음 시도에서 지운다", async () => {
    let fail = true;
    const { result, target } = setup(async () => {
      if (fail) throw new ApiError(422, { code: "validation_failed", message: "x", details: { issues: [{ path: "/pick", message: "필수" }] } });
      return pendingInteraction("i1");
    });
    let ok = true;
    await act(async () => {
      ok = await result.current.respond(target, {});
    });
    expect(ok).toBe(false);
    expect(result.current.errorsOf("i1").map((e) => e.message)).toEqual(["필수"]);
    fail = false;
    await act(async () => {
      ok = await result.current.respond(target, { pick: "v" });
    });
    expect(ok).toBe(true);
    expect(result.current.errorsOf("i1")).toEqual([]);
  });

  it("422인데 필드로 매핑되지 않으면 서버 메시지로 던진다", async () => {
    const { result, target } = setup(async () => {
      throw new ApiError(422, { code: "validation_failed", message: "서버 설명" });
    });
    await act(async () => {
      await expect(result.current.respond(target, {})).rejects.toThrow("서버 설명");
    });
  });

  it("네트워크 오류(status 0): 입력이 유지된다는 안내로 던지고, 닫힘 처리는 하지 않는다", async () => {
    const { result, spies, target } = setup(async () => {
      throw new ApiError(0, { code: "network_error", message: "fetch failed" });
    });
    await act(async () => {
      await expect(result.current.respond(target, {})).rejects.toThrow(/연결이 끊겨/);
    });
    expect(spies.applyInteraction).not.toHaveBeenCalled();
    expect(spies.notify).not.toHaveBeenCalled();
  });
});
