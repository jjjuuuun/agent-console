// 워크스페이스 계산(순수 함수): 폴더 패턴 맞추기, 사내 패키지 판별, 의존 닫힘(closure), tarball 이름.

/** 사내 패키지 이름 접두사 기본값. 호출자가 바꿀 수 있다. */
export const DEFAULT_IN_HOUSE_PREFIXES = ["@agent-console/"];

/**
 * @param {string} name 패키지 이름
 * @param {string[]} [prefixes]
 * @returns {boolean}
 */
export function isInHouse(name, prefixes = DEFAULT_IN_HOUSE_PREFIXES) {
  return prefixes.some((p) => name.startsWith(p));
}

/**
 * `pnpm-workspace.yaml`의 `packages:` 목록을 읽는다(목록 형식만 지원, 의존 없음).
 * 앞에 `!`가 붙은 제외 패턴은 `exclude`로 돌려준다.
 * @param {string} yamlText
 * @returns {{include: string[], exclude: string[]}}
 */
export function readWorkspacePatterns(yamlText) {
  const include = [];
  const exclude = [];
  let inPackages = false;
  for (const raw of yamlText.replace(/\r\n?/g, "\n").split("\n")) {
    if (/^\S/.test(raw)) inPackages = /^packages\s*:/.test(raw);
    else if (inPackages) {
      const m = /^\s*-\s*["']?([^"'#\s]+)["']?/.exec(raw);
      if (!m) continue;
      if (m[1].startsWith("!")) exclude.push(m[1].slice(1));
      else include.push(m[1]);
    }
  }
  return { include, exclude };
}

/**
 * 폴더 패턴(예: `packages/ts/*` 또는 `packages/ts` 아래 두 단계 패턴)에 상대 경로가 맞는지 본다. `*`는 한 단계, `**`는 여러 단계.
 * @param {string} pattern
 * @param {string} relDir `/` 구분 상대 경로
 * @returns {boolean}
 */
export function matchesPattern(pattern, relDir) {
  const p = pattern.replace(/\/+$/, "").split("/");
  const d = relDir.replace(/\/+$/, "").split("/");
  const go = (i, j) => {
    if (i === p.length) return j === d.length;
    if (p[i] === "**") return go(i + 1, j) || (j < d.length && go(i, j + 1));
    if (j >= d.length) return false;
    const re = new RegExp(`^${p[i].replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^/]*")}$`);
    return re.test(d[j]) && go(i + 1, j + 1);
  };
  return go(0, 0);
}

/**
 * 폴더가 워크스페이스 패턴에 들어 있는지 본다(제외 패턴 반영).
 * @param {{include: string[], exclude: string[]}} patterns
 * @param {string} relDir
 * @returns {boolean}
 */
export function isCovered(patterns, relDir) {
  return patterns.include.some((p) => matchesPattern(p, relDir)) && !patterns.exclude.some((p) => matchesPattern(p, relDir));
}

const DEP_FIELDS = ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"];

/**
 * @param {Record<string, any>} packageJson
 * @returns {Record<string, string>} 모든 의존 필드를 합친 이름 -> 범위
 */
export function allDependencies(packageJson) {
  const out = {};
  for (const f of DEP_FIELDS) Object.assign(out, packageJson[f] ?? {});
  return out;
}

/**
 * 한 패키지가 (직접·간접으로) 필요로 하는 사내 패키지를 의존되는 쪽이 먼저 오도록 돌려준다.
 * @param {string} name 시작 패키지 이름
 * @param {{name: string, packageJson: Record<string, any>}[]} packages 워크스페이스 패키지 전부
 * @param {string[]} [prefixes]
 * @returns {{order: string[], missing: string[]}} order는 시작 패키지를 뺀 위상 순서, missing은 워크스페이스에 없는 사내 의존
 * @throws {Error} 순환 의존
 */
export function inHouseClosure(name, packages, prefixes = DEFAULT_IN_HOUSE_PREFIXES) {
  const byName = new Map(packages.map((p) => [p.name, p]));
  const order = [];
  const missing = new Set();
  const state = new Map();
  const visit = (n, trail) => {
    if (state.get(n) === "done") return;
    if (state.get(n) === "doing") throw new Error(`순환 의존: ${[...trail, n].join(" -> ")}`);
    state.set(n, "doing");
    const pkg = byName.get(n);
    if (!pkg) missing.add(n);
    else {
      for (const dep of Object.keys(allDependencies(pkg.packageJson)).filter((d) => isInHouse(d, prefixes)).sort()) {
        visit(dep, [...trail, n]);
      }
    }
    state.set(n, "done");
    if (n !== name && pkg) order.push(n);
  };
  visit(name, []);
  return { order, missing: [...missing].sort() };
}

/**
 * `pnpm pack`이 만드는 tarball 파일 이름: `@scope/name` 1.2.3 -> `scope-name-1.2.3.tgz`.
 * @param {string} name
 * @param {string} version
 * @returns {string}
 */
export function tarballName(name, version) {
  return `${name.replace(/^@/, "").replace("/", "-")}-${version}.tgz`;
}

/**
 * 이름에서 scope 접두사를 뽑는다: `@acme/x` -> `@acme/`. scope가 없으면 null.
 * @param {string | undefined} name
 * @returns {string | null}
 */
export function prefixOf(name) {
  const m = /^(@[^/]+\/)/.exec(name ?? "");
  return m ? m[1] : null;
}

/**
 * 사내 접두사를 정한다. 우선순위: 명시(`--prefix`) > 루트 package.json 이름의 scope > 워크스페이스 패키지 scope들 > 기본값.
 * @param {{explicit?: string[], rootPackageJson?: Record<string, any> | null, packageNames?: string[]}} args
 * @returns {string[]}
 */
export function resolvePrefixes({ explicit = [], rootPackageJson = null, packageNames = [] }) {
  if (explicit.length) return explicit.map((p) => (p.endsWith("/") ? p : `${p}/`));
  const root = prefixOf(rootPackageJson?.name);
  if (root) return [root];
  const scopes = [...new Set(packageNames.map(prefixOf).filter(Boolean))];
  return scopes.length ? scopes : DEFAULT_IN_HOUSE_PREFIXES;
}
