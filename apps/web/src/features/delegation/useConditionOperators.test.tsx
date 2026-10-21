import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModuleInfo } from "@agent-console/contracts";
import { ApiProvider } from "../../app/ApiContext";
import { createAppQueryClient } from "../../app/queries";
import { LINK_PART_IDS, LinkPartsProvider, ModulesProvider, type LinkPartDef } from "../../modules";
import { createFakeClients } from "../../testing/fakes";
import { useConditionOperators } from "./useConditionOperators";

// 연동 부분 등록 데이터(앱 조립 층 `links/`는 기능 폴더가 import하지 않는다): 연산자 목록은 실행 역할이 있을 때만
const PARTS: readonly LinkPartDef[] = [{ id: LINK_PART_IDS.teamsConditionOperators, requires: ["runs"], onMissing: "hide" }];

afterEach(cleanup);

// 임의 모듈·역할: 연산자 목록은 `runs` 역할이 있을 때만 부른다(연동 부분 teams.condition-operators).
const mod = (roles: string[], status = "active"): ModuleInfo => ({ id: "any-mod", kind: "k", version: "1", status, web_roles: roles });

function setup(modules: ModuleInfo[] | "none", operators: () => Promise<unknown>) {
  const { clients, rest } = createFakeClients({ listConditionOperators: vi.fn(operators), ...(modules === "none" ? {} : { listModules: vi.fn(async () => modules) }) });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={createAppQueryClient({ retry: false })}>
      <ApiProvider clients={clients}>
        <ModulesProvider>
          <LinkPartsProvider parts={PARTS}>{children}</LinkPartsProvider>
        </ModulesProvider>
      </ApiProvider>
    </QueryClientProvider>
  );
  return { rest, ...renderHook(() => useConditionOperators(), { wrapper }) };
}

describe("useConditionOperators", () => {
  it("실행 역할이 있으면 서버 목록을 읽어 ready", async () => {
    const { result, rest } = setup([mod(["runs"])], async () => [{ id: "o1", title: "하나" }]);
    await waitFor(() => expect(result.current.state).toBe("ready"));
    expect(result.current.operators).toEqual([{ id: "o1", title: "하나" }]);
    expect(rest.listConditionOperators).toHaveBeenCalledTimes(1);
  });
  it("실행 역할이 없으면(연동 꺼짐) 목록을 부르지 않고 absent", async () => {
    const { result, rest } = setup([mod(["conversations"])], async () => []);
    await waitFor(() => expect(result.current.state).toBe("absent"));
    expect(result.current.operators).toBeNull();
    expect(rest.listConditionOperators).not.toHaveBeenCalled();
  });
  it("모듈 목록을 못 받으면(fail-open) 요청해 보고, 실패하면 error + 다시 시도", async () => {
    let fail = true;
    const { result, rest } = setup("none", async () => {
      if (fail) throw new Error("x");
      return [{ id: "o2", title: "둘" }];
    });
    await waitFor(() => expect(result.current.state).toBe("error"));
    fail = false;
    result.current.retry();
    await waitFor(() => expect(result.current.state).toBe("ready"));
    expect(rest.listConditionOperators).toHaveBeenCalledTimes(2);
  });
});
