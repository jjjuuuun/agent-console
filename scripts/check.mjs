// `pnpm check [vitest 인자...]`: lint -> pkg-lint -> typecheck -> test -> deps 를 차례로 돌린다.
// 추가 인자는 test 단계(vitest run)에만 전달한다. pnpm이 `a && b && c` 스크립트 끝에 인자를 붙여 deps 단계로 새는 문제를 막는다.
import { spawnSync } from "node:child_process";

const extra = process.argv.slice(2).filter((a) => a !== "--");
const steps = [
  ["lint", []],
  ["pkg-lint", []],
  ["typecheck", []],
  ["test", extra],
  ["deps", []],
];
for (const [name, args] of steps) {
  console.log(`\n> pnpm ${name}${args.length > 0 ? ` ${args.join(" ")}` : ""}`);
  const r = spawnSync("pnpm", [name, ...args], { stdio: "inherit", shell: process.platform === "win32" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}
