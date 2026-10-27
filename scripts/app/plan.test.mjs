import { describe, expect, it } from "vitest";

import {
  AppArgsError,
  DEFAULT_SERVER_PORT,
  DEFAULT_WEB_PORT,
  buildPlan,
  parseAppArgs,
  urlHost,
  webOrigins,
  wslHint,
} from "./plan.mjs";

describe("parseAppArgs", () => {
  it("기본값은 서버·vite 기본 주소", () => {
    const o = parseAppArgs([], {});
    expect(o).toMatchObject({ host: "127.0.0.1", port: DEFAULT_SERVER_PORT, webPort: DEFAULT_WEB_PORT, build: false, serveArgs: [] });
  });

  it("인자 > 환경변수, -- 뒤는 serve로 넘김", () => {
    const o = parseAppArgs(["--port=9001", "--web-port", "5000", "--config", "a.yaml", "--build", "--", "--disable-module", "x"], {
      AGENT_CONSOLE_PORT: "9999",
      AGENT_CONSOLE_WEB_HOST: "localhost",
    });
    expect(o).toMatchObject({ port: 9001, webPort: 5000, webHost: "localhost", config: "a.yaml", build: true, serveArgs: ["--disable-module", "x"] });
  });

  it("잘못된 입력은 AppArgsError", () => {
    expect(() => parseAppArgs(["--nope"], {})).toThrow(AppArgsError);
    expect(() => parseAppArgs(["--port", "0"], {})).toThrow(AppArgsError);
    expect(() => parseAppArgs(["--port"], {})).toThrow(AppArgsError);
    expect(() => parseAppArgs([], { AGENT_CONSOLE_WEB_PORT: "abc" })).toThrow(AppArgsError);
  });
});

describe("출처·주소", () => {
  it("루프백 이름은 두 출처 모두, 그 밖은 그대로", () => {
    expect(webOrigins("127.0.0.1", 4173)).toEqual(["http://127.0.0.1:4173", "http://localhost:4173"]);
    expect(webOrigins("::1", 4173)).toEqual(["http://[::1]:4173"]);
    expect(urlHost("0.0.0.0")).toBe("127.0.0.1");
    expect(urlHost("::")).toBe("[::1]");
  });
});

describe("buildPlan", () => {
  it("서버에 웹 출처를 덧붙이고, 웹 프록시 대상을 서버 주소로", () => {
    const plan = buildPlan(parseAppArgs(["--port", "9100", "--", "--disable-module", "mod-exports"], {}), { env: {}, webDistExists: true });
    expect(plan.build).toBeNull();
    expect(plan.server.command).toBe("uv");
    expect(plan.server.args).toEqual([
      "run", "agent-console", "serve", "--host", "127.0.0.1", "--port", "9100",
      "--allow-origin", "http://127.0.0.1:4173", "--allow-origin", "http://localhost:4173",
      "--disable-module", "mod-exports",
    ]);
    expect(plan.web.args).toEqual(["--filter", "@agent-console/web", "preview", "--host", "127.0.0.1", "--port", "4173", "--strictPort"]);
    expect(plan.web.env).toEqual({ AGENT_CONSOLE_SERVER_URL: "http://127.0.0.1:9100" });
    expect(plan.urls).toEqual({ server: "http://127.0.0.1:9100", web: "http://127.0.0.1:4173" });
  });

  it("빌드본이 없거나 --build면 먼저 빌드", () => {
    expect(buildPlan(parseAppArgs([], {}), { env: {}, webDistExists: false }).build?.args).toEqual(["--filter", "@agent-console/web", "build"]);
    expect(buildPlan(parseAppArgs(["--build"], {}), { env: {}, webDistExists: true }).build).not.toBeNull();
  });

  it("설정 파일을 serve로 넘기고, 명시한 프록시 대상은 유지", () => {
    const plan = buildPlan(parseAppArgs(["--config", "my.yaml"], {}), { env: { AGENT_CONSOLE_SERVER_URL: "http://x:1" }, webDistExists: true });
    expect(plan.server.args).toContain("--config");
    expect(plan.web.env.AGENT_CONSOLE_SERVER_URL).toBe("http://x:1");
  });
});

describe("wslHint", () => {
  const procVersion = "Linux version 6.6 (microsoft-standard-WSL2)";
  it("WSL /mnt에서 uv 환경변수가 없으면 안내", () => {
    expect(wslHint({ platform: "linux", cwd: "/mnt/c/x", env: {}, procVersion })).toContain("UV_PROJECT_ENVIRONMENT");
  });
  it("해당 없으면 null", () => {
    expect(wslHint({ platform: "linux", cwd: "/home/u/x", env: {}, procVersion })).toBeNull();
    expect(wslHint({ platform: "win32", cwd: "/mnt/c/x", env: {}, procVersion })).toBeNull();
    expect(wslHint({ platform: "linux", cwd: "/mnt/c/x", env: { UV_PROJECT_ENVIRONMENT: "a", UV_LINK_MODE: "copy" }, procVersion })).toBeNull();
    expect(wslHint({ platform: "linux", cwd: "/mnt/c/x", env: {}, procVersion: "Linux version 6.1 generic" })).toBeNull();
  });
});
