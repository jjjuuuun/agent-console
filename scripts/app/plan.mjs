// `pnpm app` 실행 계획(순수 함수). 프로세스를 띄우지 않고 "무엇을 어떤 인자·환경으로 띄울지"만 계산한다.
// 실행은 scripts/app.mjs가 한다. 포트·주소·경로는 인자 > 환경변수 > 기본값(서버·Vite 기본값과 같은 값) 순서로 정한다.
// 설계: specs/agent-console/design.md §R6·§R7(서버와 웹은 별도 프로세스, 웹 출처는 서버 허용 출처에 명시).

/** 서버 기본 바인딩(서버 설정 기본값과 같다). */
export const DEFAULT_SERVER_HOST = "127.0.0.1";
export const DEFAULT_SERVER_PORT = 8765;
/** 웹 미리보기 기본 주소(vite preview 기본 포트). */
export const DEFAULT_WEB_HOST = "127.0.0.1";
export const DEFAULT_WEB_PORT = 4173;
export const WEB_PACKAGE = "@agent-console/web";

export const USAGE = `사용: pnpm app [옵션] [-- serve 추가 인자]

서버(uv run agent-console serve)와 웹 미리보기(vite preview)를 함께 띄운다. Ctrl-C로 둘 다 끝낸다.

옵션:
  --host H        서버 바인딩 주소   (환경 AGENT_CONSOLE_HOST, 기본 ${DEFAULT_SERVER_HOST})
  --port N        서버 포트          (환경 AGENT_CONSOLE_PORT, 기본 ${DEFAULT_SERVER_PORT})
  --web-host H    웹 미리보기 주소   (환경 AGENT_CONSOLE_WEB_HOST, 기본 ${DEFAULT_WEB_HOST})
  --web-port N    웹 미리보기 포트   (환경 AGENT_CONSOLE_WEB_PORT, 기본 ${DEFAULT_WEB_PORT})
  --config PATH   서버 설정 파일     (없으면 AGENT_CONSOLE_CONFIG → ./agent-console.yaml)
  --build         웹을 다시 빌드한다(apps/web/dist가 없으면 항상 빌드)
  -h, --help      이 도움말

예: pnpm app -- --apply-preset solo-assistant`;

export class AppArgsError extends Error {}

/**
 * 명령행 인자를 읽는다.
 * @param {string[]} argv `process.argv.slice(2)`
 * @param {Record<string, string | undefined>} env 환경변수
 * @returns {{help: boolean, host: string, port: number, webHost: string, webPort: number,
 *   config: string | undefined, build: boolean, serveArgs: string[]}}
 * @throws {AppArgsError} 모르는 옵션·잘못된 포트
 */
export function parseAppArgs(argv, env) {
  const opts = {
    help: false,
    host: env.AGENT_CONSOLE_HOST || DEFAULT_SERVER_HOST,
    port: env.AGENT_CONSOLE_PORT || String(DEFAULT_SERVER_PORT),
    webHost: env.AGENT_CONSOLE_WEB_HOST || DEFAULT_WEB_HOST,
    webPort: env.AGENT_CONSOLE_WEB_PORT || String(DEFAULT_WEB_PORT),
    config: undefined,
    build: false,
    serveArgs: [],
  };
  const valued = { "--host": "host", "--port": "port", "--web-host": "webHost", "--web-port": "webPort", "--config": "config" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--") {
      opts.serveArgs = argv.slice(i + 1);
      break;
    }
    if (arg === "-h" || arg === "--help") {
      opts.help = true;
      continue;
    }
    if (arg === "--build") {
      opts.build = true;
      continue;
    }
    const [name, inline] = arg.includes("=") ? [arg.slice(0, arg.indexOf("=")), arg.slice(arg.indexOf("=") + 1)] : [arg, undefined];
    const key = valued[name];
    if (!key) throw new AppArgsError(`모르는 옵션: ${arg}`);
    const value = inline ?? argv[(i += 1)];
    if (value === undefined || value === "") throw new AppArgsError(`${name}에 값이 필요합니다`);
    opts[key] = value;
  }
  return { ...opts, port: toPort(opts.port, "--port"), webPort: toPort(opts.webPort, "--web-port") };
}

function toPort(value, name) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new AppArgsError(`${name}는 1~65535 정수여야 합니다`);
  return port;
}

const LOOPBACK_NAMES = new Set(["127.0.0.1", "localhost"]);

/** URL에 넣을 호스트(IPv6는 대괄호). 와일드카드 바인딩은 같은 기계의 루프백으로 접속한다. */
export function urlHost(host) {
  const name = host === "0.0.0.0" || host === "" ? "127.0.0.1" : host === "::" ? "::1" : host;
  return name.includes(":") && !name.startsWith("[") ? `[${name}]` : name;
}

/**
 * 서버에 덧붙일 웹 출처. 루프백 이름(127.0.0.1·localhost)은 브라우저에서 어느 쪽으로 열어도 되게 둘 다 넣는다.
 * @param {string} webHost
 * @param {number} webPort
 * @returns {string[]}
 */
export function webOrigins(webHost, webPort) {
  const host = urlHost(webHost);
  const hosts = LOOPBACK_NAMES.has(host) ? [...LOOPBACK_NAMES] : [host];
  return hosts.map((h) => `http://${h}:${webPort}`);
}

/**
 * WSL의 Windows 드라이브(/mnt/…)에서 uv 환경변수가 없을 때 보일 안내(CLAUDE.md 환경 메모). 해당 없으면 null.
 * @param {{platform: string, cwd: string, env: Record<string, string | undefined>, procVersion: string}} host
 */
export function wslHint({ platform, cwd, env, procVersion }) {
  if (platform !== "linux") return null;
  const wsl = Boolean(env.WSL_DISTRO_NAME) || /microsoft/i.test(procVersion);
  if (!wsl || !cwd.startsWith("/mnt/")) return null;
  const missing = ["UV_PROJECT_ENVIRONMENT", "UV_LINK_MODE"].filter((k) => !env[k]);
  if (missing.length === 0) return null;
  return [
    `WSL /mnt 경로에서 ${missing.join("·")}가 비어 있습니다. Windows 쪽 도구와 .venv를 공유하지 않도록 다음을 권장합니다:`,
    "  UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv pnpm app",
  ].join("\n");
}

/**
 * 실행 계획.
 * @param {ReturnType<typeof parseAppArgs>} opts
 * @param {{env: Record<string, string | undefined>, webDistExists: boolean}} ctx
 * @returns {{build: {command: string, args: string[]} | null,
 *   server: {command: string, args: string[], env: Record<string, string>},
 *   web: {command: string, args: string[], env: Record<string, string>},
 *   urls: {server: string, web: string}}}
 */
export function buildPlan(opts, { env, webDistExists }) {
  const serverUrl = `http://${urlHost(opts.host)}:${opts.port}`;
  const webUrl = `http://${urlHost(opts.webHost)}:${opts.webPort}`;
  const serveArgs = ["run", "agent-console", "serve", "--host", opts.host, "--port", String(opts.port)];
  if (opts.config) serveArgs.push("--config", opts.config);
  for (const origin of webOrigins(opts.webHost, opts.webPort)) serveArgs.push("--allow-origin", origin);
  serveArgs.push(...opts.serveArgs);
  return {
    build: opts.build || !webDistExists ? { command: "pnpm", args: ["--filter", WEB_PACKAGE, "build"] } : null,
    server: { command: "uv", args: serveArgs, env: {} },
    web: {
      command: "pnpm",
      args: ["--filter", WEB_PACKAGE, "preview", "--host", opts.webHost, "--port", String(opts.webPort), "--strictPort"],
      // apps/web/vite.config.ts의 /api·/ws 프록시 대상(미리보기도 server.proxy를 그대로 쓴다).
      env: { AGENT_CONSOLE_SERVER_URL: env.AGENT_CONSOLE_SERVER_URL || serverUrl },
    },
    urls: { server: serverUrl, web: webUrl },
  };
}
