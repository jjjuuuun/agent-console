// 계약 JSON Schema → TypeScript 타입 생성 (design §5.7).
// 사용: node scripts/generate.js [--check]
//   (인자 없음) schema/agent-console.schema.json → src/generated/contracts.generated.ts 와
//               하위 모듈별 파일 src/generated/<하위 모듈>.ts(스키마 `x-modules`)를 쓴다.
//               하위 모듈 파일은 `@agent-console/contracts/<하위 모듈>` 하위 경로의 진입점이다.
//               상수만 다시 내보내는 src/generated/constants.ts(`@agent-console/contracts/constants`)도 쓴다.
//   --check     다시 생성한 내용과 커밋된 파일이 다르면 exit 1 (드리프트 검사).
// 스키마 자체는 Python(`python -m agent_console_contracts export`)이 만든다. 전체 생성은 `uv run poe contracts`.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const pkgRoot = fileURLToPath(new URL("..", import.meta.url));
const schemaPath = `${pkgRoot}schema/agent-console.schema.json`;
const outDir = `${pkgRoot}src/generated`;

const BANNER = `/* eslint-disable */
/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */`;

const TYPE_KEYS = ["type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const", "properties", "items"];
const SCHEMA_MAP_KEYS = ["properties", "$defs", "patternProperties"];
const SCHEMA_LIST_KEYS = ["anyOf", "oneOf", "allOf", "prefixItems"];
const SCHEMA_KEYS = ["items", "additionalProperties", "not"];

/**
 * 생성기 입력용 전처리(스키마 파일은 바꾸지 않는다).
 * - 속성 수준 `title`(폼 라벨용)은 json-schema-to-typescript가 별도 타입 이름으로 쓰지 않게 지운다.
 * - `$defs` 바로 아래(모델)의 `title`은 화면 표시명(한국어 등)일 수 있으므로, 타입 이름이 되도록
 *   `$defs` 키(= Python 모델 이름)로 바꾼다.
 * - 타입 제약이 없는 스키마(Python `Any`)는 `unknown`으로 표시한다(기본 변환은 객체로 추론).
 * - `$ref` 옆의 형제 키(설명 등)는 지운다. 남기면 생성기가 같은 모델을 `Name1`처럼 새 타입으로 복제한다.
 * - 루트의 `x-constants`는 타입이 아니라 상수로 따로 내보낸다. `x-modules`(하위 모듈 → 모델 이름)는
 *   하위 경로 파일을 만들 때만 쓴다.
 */
function prepare(schema, isNamed) {
  if (schema === null || typeof schema !== "object" || Array.isArray(schema)) return schema;
  if (!isNamed && typeof schema.$ref === "string") return { $ref: schema.$ref };
  const out = {};
  for (const [key, value] of Object.entries(schema)) {
    if (key === "x-constants" || key === "x-modules" || (key === "title" && !isNamed)) continue;
    if (SCHEMA_MAP_KEYS.includes(key)) {
      out[key] = Object.fromEntries(
        Object.entries(value).map(([name, sub]) => [
          name,
          key === "$defs" ? withTypeName(prepare(sub, true), name) : prepare(sub, false),
        ]),
      );
    } else if (SCHEMA_LIST_KEYS.includes(key)) {
      out[key] = value.map((sub) => prepare(sub, false));
    } else if (SCHEMA_KEYS.includes(key)) {
      out[key] = prepare(value, false);
    } else {
      out[key] = value;
    }
  }
  if (!isNamed && !TYPE_KEYS.some((key) => key in schema)) out.tsType = "unknown";
  return out;
}

/** 모델 스키마의 `title`(있을 때만)을 타입 이름으로 고정한다. */
function withTypeName(schema, name) {
  if (schema === null || typeof schema !== "object" || !("title" in schema)) return schema;
  return { ...schema, title: name };
}

function renderConstants(constants) {
  return Object.entries(constants)
    .map(([name, value]) => `export const ${name} = ${JSON.stringify(value, null, 2)} as const;`)
    .join("\n\n");
}

/** 하위 모듈 하나의 진입 파일: 그 하위 모듈에 정의된 타입 다시 내보내기 + 하위 모듈 이름·버전. */
function renderSubmodule(name, typeNames, version) {
  const lines = [BANNER.replace("/* eslint-disable */\n", ""), "", `// 계약 하위 모듈 \`${name}\`: @agent-console/contracts/${name}`];
  if (typeNames.length > 0) {
    lines.push("export type {", ...typeNames.map((type) => `  ${type},`), '} from "./contracts.generated";');
  }
  lines.push("", `export const CONTRACT_MODULE = ${JSON.stringify(name)} as const;`);
  lines.push(`export const CONTRACT_VERSION = ${JSON.stringify(version ?? "")} as const;`);
  return `${lines.join("\n")}\n`;
}

/**
 * 상수 전용 진입 파일 `@agent-console/contracts/constants`: `x-constants`의 값만 다시 내보낸다.
 * 루트 진입점(스키마 JSON 전체를 싣는다)을 거치지 않고 값 상수만 쓰려는 패키지(예: projects)용.
 */
function renderConstantsEntry(names) {
  const lines = [BANNER.replace("/* eslint-disable */\n", ""), "", "// 계약 상수(schema x-constants): @agent-console/contracts/constants"];
  if (names.length > 0) {
    lines.push("export {", ...names.map((name) => `  ${name},`), '} from "./contracts.generated";');
  }
  return `${lines.join("\n")}\n`;
}

/** 생성할 파일 전체: 파일 이름 → 내용. */
export async function generateFiles() {
  const schema = JSON.parse(await readFile(schemaPath, "utf8"));
  const files = { "contracts.generated.ts": await generate(schema) };
  const versions = schema["x-constants"]?.CONTRACT_VERSIONS ?? {};
  files["constants.ts"] = renderConstantsEntry(Object.keys(schema["x-constants"] ?? {}));
  for (const [name, typeNames] of Object.entries(schema["x-modules"] ?? {})) {
    if (!/^[a-z][a-z0-9_]*$/.test(name) || name === "contracts" || name === "constants") {
      throw new Error(`쓸 수 없는 하위 모듈 이름: ${name}`);
    }
    files[`${name}.ts`] = renderSubmodule(name, typeNames, versions[name]);
  }
  return files;
}

export async function generate(schemaArg) {
  const schema = schemaArg ?? JSON.parse(await readFile(schemaPath, "utf8"));
  const prepared = prepare(schema, true);
  const types = await compile(prepared, "AgentConsoleContracts", {
    bannerComment: "",
    additionalProperties: false,
    unreachableDefinitions: true,
    declareExternallyReferenced: true,
    format: true,
    strictIndexSignatures: false,
    style: { printWidth: 100, singleQuote: false, trailingComma: "all", endOfLine: "lf" },
  });
  const constants = renderConstants(schema["x-constants"] ?? {});
  return `${BANNER}\n\n${types.trim()}\n\n// ---- 상수 (schema x-constants)\n\n${constants}\n`;
}

async function main() {
  const files = await generateFiles();
  if (process.argv.includes("--check")) {
    let stale = false;
    for (const [name, content] of Object.entries(files)) {
      const path = `${outDir}/${name}`;
      const current = await readFile(path, "utf8")
        .then((text) => text.replace(/\r\n/g, "\n"))
        .catch(() => "");
      if (current !== content) {
        console.error(`계약 드리프트: ${path} 가 스키마에서 생성한 내용과 다릅니다.`);
        stale = true;
      }
    }
    if (stale) {
      console.error("`uv run poe contracts`로 다시 생성하고 결과를 커밋하세요.");
      process.exit(1);
    }
    console.log("계약 TS 타입 최신 상태");
    return;
  }
  await mkdir(outDir, { recursive: true });
  for (const [name, content] of Object.entries(files)) {
    await writeFile(`${outDir}/${name}`, content, "utf8");
    console.log(`생성: ${outDir}/${name}`);
  }
}

await main();
