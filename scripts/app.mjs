// `pnpm app`: 서버와 웹 미리보기를 함께 띄우는 개발 편의 실행기(design §R6·§R7, 필수 아님).
// 계획(인자·환경·출처)은 scripts/app/plan.mjs의 순수 함수가 만들고, 여기서는 프로세스만 다룬다.
// 하나가 끝나면 다른 하나도 끝낸다. Ctrl-C(SIGINT)·SIGTERM은 두 프로세스 묶음(자식 포함)에 전달한다.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { AppArgsError, USAGE, buildPlan, parseAppArgs, wslHint } from "./app/plan.mjs";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const windows = process.platform === "win32";
const STOP_GRACE_MS = 5000;

function readProcVersion() {
  try {
    return readFileSync("/proc/version", "utf8");
  } catch {
    return "";
  }
}

let opts;
try {
  opts = parseAppArgs(process.argv.slice(2), process.env);
} catch (err) {
  if (!(err instanceof AppArgsError)) throw err;
  console.error(`pnpm app: ${err.message}\n\n${USAGE}`);
  process.exit(2);
}
if (opts.help) {
  console.log(USAGE);
  process.exit(0);
}

const hint = wslHint({ platform: process.platform, cwd: repo, env: process.env, procVersion: readProcVersion() });
if (hint) console.warn(`[app] ${hint}`);

const plan = buildPlan(opts, { env: process.env, webDistExists: existsSync(join(repo, "apps/web/dist/index.html")) });

if (plan.build) {
  console.log("[app] 웹 빌드 중 (pnpm --filter @agent-console/web build)…");
  const built = spawnSync(plan.build.command, plan.build.args, { cwd: repo, stdio: "inherit", shell: windows });
  if (built.status !== 0) {
    console.error("[app] 웹 빌드 실패");
    process.exit(built.status ?? 1);
  }
}

/** @type {{name: string, child: import("node:child_process").ChildProcess}[]} */
const procs = [];
let stopping = false;
let exitCode = 0;

function start(name, step) {
  const child = spawn(step.command, step.args, {
    cwd: repo,
    stdio: "inherit",
    env: { ...process.env, ...step.env },
    shell: windows,
    // POSIX: 자식마다 프로세스 묶음을 따로 만들어 uv·pnpm 아래 손자 프로세스까지 한 번에 끝낸다.
    detached: !windows,
  });
  child.on("exit", (code, signal) => {
    if (!stopping) {
      console.log(`[app] ${name} 종료(${signal ?? code}) — 나머지도 끝냅니다`);
      exitCode = code ?? 1;
      stopAll("SIGTERM");
    }
    if (procs.every((p) => p.child.exitCode !== null || p.child.signalCode !== null)) process.exit(exitCode);
  });
  child.on("error", (err) => {
    console.error(`[app] ${name} 시작 실패: ${err.message}`);
    exitCode = 1;
    stopAll("SIGTERM");
  });
  procs.push({ name, child });
}

function kill(child, signal) {
  if (child.pid === undefined || child.exitCode !== null || child.signalCode !== null) return;
  try {
    if (windows) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else process.kill(-child.pid, signal);
  } catch {
    // 이미 끝났다.
  }
}

function stopAll(signal) {
  if (stopping) return;
  stopping = true;
  for (const { child } of procs) kill(child, signal);
  setTimeout(() => {
    for (const { child } of procs) kill(child, "SIGKILL");
    process.exit(exitCode);
  }, STOP_GRACE_MS).unref();
}

for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => stopAll(sig));

start("서버", plan.server);
start("웹 미리보기", plan.web);
console.log(`[app] 서버 ${plan.urls.server}  ·  웹 ${plan.urls.web}  (Ctrl-C로 둘 다 종료)`);
