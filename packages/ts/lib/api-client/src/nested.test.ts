import { describe, expect, it } from "vitest";
import { createRestClient, type FetchLike } from "./index";

/** 5R.17: 중첩 팀(자식 Run)·조건 연산자 경로. 메서드·경로·쿼리만 확인한다. */
function fake(body: unknown) {
  const calls: string[] = [];
  const fn: FetchLike = (url, init = {}) => {
    calls.push(`${init.method ?? "GET"} ${url.replace("http://h/api/v1", "")}`);
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  };
  return { calls, rest: createRestClient({ baseUrl: "http://h", token: "T", fetch: fn }) };
}

describe("중첩 팀·조건 연산자 경로", () => {
  it("조건 연산자 목록은 GET /condition-operators", async () => {
    const { calls, rest } = fake([{ id: "x", title: "X" }]);
    const list = await rest.listConditionOperators();
    expect(calls).toEqual(["GET /condition-operators"]);
    expect(list[0]?.id).toBe("x");
  });
  it("루트 기준 Run·상호작용 조회는 root 쿼리를 보낸다", async () => {
    const { calls, rest } = fake([]);
    await rest.listRuns({ root: "r 1", limit: 5 });
    await rest.listInteractions({ root: "r1", status: "pending" });
    expect(calls).toEqual(["GET /runs?root=r%201&limit=5", "GET /interactions?root=r1&status=pending"]);
  });
  it("Run 스냅샷의 children을 그대로 돌려준다", async () => {
    const { rest } = fake({ run: { id: "r" }, node_runs: [], last_seq: 0, children: [{ id: "c1" }] });
    expect((await rest.getRun("r")).children?.[0]?.id).toBe("c1");
  });
});
