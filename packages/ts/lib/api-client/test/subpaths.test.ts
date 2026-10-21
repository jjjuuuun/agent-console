import { describe, expect, it } from "vitest";
import { createCoreClient } from "@agent-console/api-client/core";
import { createChatClient } from "@agent-console/api-client/chat";
import { createRestIo } from "@agent-console/api-client/transport";
import { createRestClient } from "@agent-console/api-client";

function fakeFetch(calls: string[]) {
  return async (url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${url.replace("http://h/api/v1", "")}`);
    return new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } });
  };
}

describe("기능별 하위 경로", () => {
  it("기능 클라이언트 하나를 전송만으로 단독 사용한다", async () => {
    const calls: string[] = [];
    const io = createRestIo({ baseUrl: "http://h", fetch: fakeFetch(calls) });
    await createChatClient(io).listConversations({ archived: false });
    await createCoreClient(io).listModules();
    await createCoreClient(io).getModuleOptions("m a");
    expect(calls).toEqual(["GET /conversations?archived=false", "GET /modules", "GET /modules/m%20a/options"]);
  });

  it("전체 클라이언트에도 모듈 목록이 있다", async () => {
    const calls: string[] = [];
    const rest = createRestClient({ baseUrl: "http://h", fetch: fakeFetch(calls) });
    expect(await rest.listModules()).toEqual([]);
    expect(calls).toEqual(["GET /modules"]);
  });
});
