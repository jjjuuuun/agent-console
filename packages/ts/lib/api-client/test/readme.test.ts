import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { createRestClient } from "@agent-console/api-client";

// fetch를 주입하므로 서버 없이도 돈다(실제로는 전역 fetch 또는 서버 주소를 쓴다).
const fakeFetch = async () =>
  new Response(JSON.stringify({ token: "t", server_version: "0.0.0", contracts_version: "0.4.0" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
const rest = createRestClient({ baseUrl: "http://127.0.0.1:8765", fetch: fakeFetch });
const boot = await rest.getBootstrap();
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(boot.token).toBe("t");
});
