import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { contractsSchema } from "@agent-console/contracts";
import { DATA_NAMES, DELEGATION_NAMES, findDataNameLiterals, isAllowedExact, isAllowedVariant } from "../testing/dataNames";

const SRC = resolve(__dirname, "..");
const REPO = resolve(SRC, "../../..");

/** 앱 소스(테스트·픽스처 제외) 파일 목록. */
function appSourceFiles(dir = SRC): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name === "testing") continue;
      out.push(...appSourceFiles(path));
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) {
      out.push(path);
    }
  }
  return out;
}

/** 기본 제공 노드 패키지의 디스크립터에서 id/category를 읽는다(새 타입이 생겨도 검사 대상이 자동으로 늘어난다). */
function builtinNames(): { ids: string[]; categories: string[] } {
  const dir = join(REPO, "packages/py/features/ac-nodes-core/src/agent_console_nodes_core");
  const ids = new Set<string>();
  const categories = new Set<string>();
  if (existsSync(dir)) {
    for (const file of readdirSync(dir).filter((f) => f.endsWith(".py"))) {
      const text = readFileSync(join(dir, file), "utf8");
      for (const m of text.matchAll(/^\s+id="([^"]+)"/gm)) ids.add(m[1]!);
      for (const m of text.matchAll(/category="([^"]+)"/g)) categories.add(m[1]!);
    }
  }
  return { ids: [...ids], categories: [...categories] };
}

/** 계약이 정의한 이벤트·메시지 type 상수(`agent.message`, `run.event` 등). 점 표기 type 중 이것만 앱이 비교해도 된다. */
function contractEventTypes(): Set<string> {
  const out = new Set<string>();
  for (const def of Object.values(contractsSchema.$defs as Record<string, { properties?: { type?: { const?: unknown } } }>)) {
    const c = def.properties?.type?.const;
    if (typeof c === "string" && c.includes(".")) out.add(c);
  }
  return out;
}

// 서버 소스를 못 읽는 환경을 위한 보조 목록(예시 이름일 뿐이며 검사용이다).
const FALLBACK_IDS = ["agent", "router", "input", "output", "human", "condition", "loop", "subgraph", "merge", "switch", "tool"];


describe("하드코딩 점검: 노드 타입·카테고리·엣지·리소스·창·모델 이름이 앱 코드에 없다", () => {
  const { ids, categories } = builtinNames();
  const forbidden = [...new Set([...ids, ...FALLBACK_IDS, ...categories, ...DATA_NAMES, ...DELEGATION_NAMES])];

  it("점검 대상이 비어 있지 않다", () => {
    expect(forbidden.length).toBeGreaterThan(5);
    expect(appSourceFiles().length).toBeGreaterThan(20);
  });

  it("따옴표로 둘러싼 문자열 리터럴로 타입·카테고리 이름을 쓰지 않는다", () => {
    const hits: string[] = [];
    for (const file of appSourceFiles()) {
      // 한글 화면 문구 표는 표시용 텍스트다(카테고리 이름과 우연히 같을 수 있다).
      // 기능 폴더의 문구 표(`features/*/messages.ts`)도 표시용 텍스트다.
      if (relative(SRC, file) === join("app", "messages.ts") || /^features[\\/][^\\/]+[\\/]messages\.ts$/.test(relative(SRC, file))) continue;
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, i) => {
        for (const name of forbidden) {
          // 서버 데이터 이름(DATA_NAMES)은 대소문자·접두·접미 변형까지, 노드 타입 id 같은 일반 낱말은 정확히 같은 문자열만 본다.
          if (DATA_NAMES.includes(name)) {
            for (const lit of findDataNameLiterals(line, name)) if (!isAllowedVariant(relative(SRC, file), lit)) hits.push(`${relative(SRC, file)}:${i + 1}  "${name}" (${lit})  ${line.trim()}`);
          } else if (new RegExp(`(["'\`])${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\1`).test(line) && !isAllowedExact(relative(SRC, file), name)) hits.push(`${relative(SRC, file)}:${i + 1}  "${name}"  ${line.trim()}`);
        }
      });
    }
    expect(hits).toEqual([]);
  }, 60_000);

  it("계약 이벤트 type 목록을 읽었다", () => {
    expect(contractEventTypes().has("run.event")).toBe(true);
  });

  it("type을 문자열로 비교하는 분기는 계약이 정의한 이벤트 type(점 표기)만 쓴다", () => {
    // 점이 있다는 이유만으로 허용하지 않는다: `node.agent` 같은 노드 종류 접두 문자열이 새어 들어가는 것을 막는다.
    const events = contractEventTypes();
    const hits: string[] = [];
    const patterns = [/\.type\s*(?:===|!==|==|!=)\s*["'`]([^"'`]+)["'`]/g, /case\s+["'`]([^"'`]+)["'`]\s*:/g];
    for (const file of appSourceFiles()) {
      const text = readFileSync(file, "utf8");
      const isTypeSwitch = /switch\s*\([^)]*\.type\s*\)/.test(text);
      for (const re of patterns) {
        if (re.source.startsWith("case") && !isTypeSwitch) continue;
        for (const m of text.matchAll(re)) {
          if (!events.has(m[1]!)) hits.push(`${relative(SRC, file)}: ${m[0]}`);
        }
      }
    }
    expect(hits).toEqual([]);
  }, 60_000);

  it("점 표기 문자열에 서버 데이터 이름이 조각으로 들어가지 않는다(계약 이벤트 type 제외)", () => {
    const events = contractEventTypes();
    const segments = new Set(forbidden);
    const hits: string[] = [];
    for (const file of appSourceFiles()) {
      const rel = relative(SRC, file);
      if (rel === join("app", "messages.ts") || /^features[\\/][^\\/]+[\\/]messages\.ts$/.test(rel)) continue;
      readFileSync(file, "utf8").split("\n").forEach((line, i) => {
        for (const m of line.matchAll(/(["'`])([A-Za-z_][\w-]*(?:\.[\w-]+)+)\1/g)) {
          const lit = m[2]!;
          if (events.has(lit)) continue;
          if (lit.split(".").some((seg) => segments.has(seg) && DATA_NAMES.includes(seg))) hits.push(`${rel}:${i + 1}  ${lit}`);
        }
      });
    }
    expect(hits).toEqual([]);
  }, 60_000);

  it("답변 자리 키(label·order·final·stream)를 연결 config에서 읽지 않는다(계획 요약 TeamPlanSummary에서만)", () => {
    // 이 키들은 연결 종류 플러그인이 `reply_fields`로 정하는 데이터다. 실행 이벤트(`run.reply`) payload를 읽는 곳과
    // 설정 화면 사용량 규칙의 무관한 같은 낱말, 사용량 표시기 항목 표(usageConfig, 표시 요소 이름),
    // 버전 비교 항목 이름 후보 키의 기본값(lib/itemLabelKeys, 사용자 설정 `ui.versions.item_label_keys`가 덮는다)만 허용한다.
    const allowed = new Set([join("features", "chat", "lib", "liveRun.ts"), join("features", "usage", "usageLib.ts"), join("features", "usage", "usageConfig.ts"), join("lib", "itemLabelKeys.ts")]);
    const hits: string[] = [];
    for (const file of appSourceFiles()) {
      const rel = relative(SRC, file);
      if (allowed.has(rel)) continue;
      readFileSync(file, "utf8").split("\n").forEach((line, i) => {
        if (/(["'`])(label|order|final|stream)\1/.test(line)) hits.push(`${rel}:${i + 1}  ${line.trim()}`);
      });
    }
    expect(hits).toEqual([]);
  }, 60_000);
});
