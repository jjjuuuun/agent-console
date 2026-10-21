// 실행 계획(순수 함수): 어떤 명령을 어떤 순서로 돌릴지만 계산한다. 프로세스는 CLI가 띄운다(scripts/app/plan.mjs 방식).
import { allDependencies, inHouseClosure, isInHouse, tarballName } from "./workspace.mjs";

/** tarball 출력 폴더 기본값(저장소 루트 기준). */
export const DEFAULT_NPM_DIR = "dist/npm";

/** pack-all이 다루는 패키지 폴더 필터 기본값. */
/**
 * 저장소 밖 복사본에서 단계를 돌릴 때 더하는 환경변수. 시간 단언이 있는 테스트는 `AGENT_CONSOLE_SKIP_PERF=1`이면
 * 시간 비교만 건너뛰고(정확성 단언은 유지) 복사 설치본의 느린 파일시스템·콜드 캐시에 흔들리지 않는다.
 */
export const PORTABILITY_ENV = Object.freeze({ AGENT_CONSOLE_SKIP_PERF: "1" });
export const DEFAULT_PACK_FILTER = "./packages/**";

/**
 * `pnpm pack:all` 계획: 빌드 스크립트가 있는 패키지를 먼저 빌드하고 전부 pack한다.
 * 루트 package.json과 앱(`apps/`)은 패키지가 아니므로 `filter`(pnpm `--filter` 값, 기본 `./packages/**`)로 제외한다.
 * @param {{outDir?: string, filter?: string}} [options]
 * @returns {{cmd: string, args: string[], label: string}[]}
 */
export function planPackAll(options = {}) {
  const outDir = options.outDir ?? DEFAULT_NPM_DIR;
  const filter = options.filter ?? DEFAULT_PACK_FILTER;
  return [
    { label: "build", cmd: "pnpm", args: ["-r", "--filter", filter, "--if-present", "build"] },
    { label: "pack", cmd: "pnpm", args: ["-r", "--filter", filter, "pack", "--pack-destination", outDir] },
  ];
}

/**
 * 이식성 검사용 package.json을 만든다: 사내 의존을 tarball `file:` 경로로 바꾸고 `overrides`에도 같은 값을 둔다.
 * 사내 peer 의존은 devDependencies로 옮겨 실제로 설치되게 한다.
 * @param {Record<string, any>} packageJson 원본
 * @param {Record<string, string>} tarballs 사내 패키지 이름 -> tarball 절대 경로
 * @param {string[]} [prefixes]
 * @returns {Record<string, any>}
 */
export function rewriteForPortability(packageJson, tarballs, prefixes) {
  const out = structuredClone(packageJson);
  const spec = (n) => `file:${tarballs[n]}`;
  for (const field of ["dependencies", "devDependencies", "optionalDependencies"]) {
    for (const dep of Object.keys(out[field] ?? {})) if (dep in tarballs && isInHouse(dep, prefixes)) out[field][dep] = spec(dep);
  }
  for (const dep of Object.keys(out.peerDependencies ?? {})) {
    if (dep in tarballs && isInHouse(dep, prefixes)) {
      delete out.peerDependencies[dep];
      out.devDependencies = { ...out.devDependencies, [dep]: spec(dep) };
    }
  }
  if (out.peerDependencies && Object.keys(out.peerDependencies).length === 0) delete out.peerDependencies;
  out.overrides = { ...(out.overrides ?? {}), ...Object.fromEntries(Object.keys(tarballs).map((n) => [n, spec(n)])) };
  delete out.pnpm;
  return out;
}

/**
 * 한 패키지의 이식성 검사 계획.
 * @param {object} args
 * @param {{name: string, packageJson: Record<string, any>}} args.pkg 검사 대상
 * @param {{name: string, version: string, packageJson: Record<string, any>}[]} args.workspace 워크스페이스 패키지 전부
 * @param {string} args.npmDir tarball이 있는 폴더(절대 경로)
 * @param {string} args.sep 경로 구분자(`/` 또는 `\\`, 기본 `/`)
 * @param {string[]} [args.prefixes]
 * @returns {{tarballs: Record<string, string>, missing: string[], rewritten: Record<string, any>, steps: {label: string, cmd: string, args: string[]}[]}}
 *   missing: 워크스페이스에 없거나 tarball 이름을 알 수 없는 사내 의존. 비어 있지 않으면 실행하지 않는다.
 */
export function planPortability({ pkg, workspace, npmDir, sep = "/", prefixes }) {
  const { order, missing } = inHouseClosure(pkg.name, workspace, prefixes);
  const byName = new Map(workspace.map((p) => [p.name, p]));
  // 직접 선언한 사내 의존도 닫힘에 포함되지만, peer는 closure에 이미 포함된다.
  const direct = Object.keys(allDependencies(pkg.packageJson)).filter((d) => isInHouse(d, prefixes));
  const names = [...new Set([...order, ...direct.filter((d) => byName.has(d))])];
  const tarballs = Object.fromEntries(names.map((n) => [n, `${npmDir.replace(/[\\/]+$/, "")}${sep}${tarballName(n, byName.get(n).version)}`]));
  return {
    tarballs,
    missing,
    rewritten: rewriteForPortability(pkg.packageJson, tarballs, prefixes),
    steps: [
      { label: "install", cmd: "npm", args: ["install", "--no-audit", "--no-fund", "--no-package-lock"] },
      ...["build", "typecheck", "test"]
        .filter((s) => pkg.packageJson.scripts?.[s])
        .map((s) => ({ label: s, cmd: "npm", args: ["run", s] })),
    ],
  };
}

/**
 * 결과 표 문자열.
 * @param {{name: string, ok: boolean, failedStep?: string, note?: string}[]} rows
 * @returns {string}
 */
export function formatResultTable(rows) {
  const width = Math.max(4, ...rows.map((r) => r.name.length));
  const lines = [`${"패키지".padEnd(width)}  결과  비고`];
  for (const r of rows) lines.push(`${r.name.padEnd(width)}  ${r.ok ? "통과" : "실패"}  ${r.ok ? (r.note ?? "") : `${r.failedStep ?? ""} ${r.note ?? ""}`.trim()}`);
  const bad = rows.filter((r) => !r.ok).length;
  lines.push(bad === 0 ? `\n전체 ${rows.length}개 통과` : `\n${bad}/${rows.length}개 실패`);
  return lines.join("\n");
}
