import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DATA_NAMES, findDataNameLiterals, isAllowedVariant } from "../testing/dataNames";

/**
 * noHardcoding.test.ts는 기능 폴더별 messages.ts(기능별 한글 문구 표)를 검사에서 뺀다.
 * 구멍이 되지 않도록, 서버 데이터 이름(연결 종류·리소스 종류·상호작용 종류·사용량 창·모델)은
 * 기능별 문구 표에도 따옴표 문자열로 나오면 안 된다. 기능 폴더가 늘면 자동으로 검사 대상이 늘어난다.
 */

const FEATURES = resolve(__dirname, "../features");
const files = readdirSync(FEATURES)
  .map((d) => join(FEATURES, d, "messages.ts"))
  .filter((f) => existsSync(f));

describe("기능별 문구 표에도 서버 데이터 이름이 없다", () => {
  it("검사 대상이 있다", () => {
    expect(files.length).toBeGreaterThan(0);
  });
  it.each(files.map((f) => [f.slice(FEATURES.length + 1), f] as const))("%s", (_name, file) => {
    const text = readFileSync(file, "utf8");
    const rel = `features/${_name.replaceAll("\\", "/")}`;
    const hits = DATA_NAMES.flatMap((n) => findDataNameLiterals(text, n)).filter((lit) => !isAllowedVariant(rel, lit));
    expect(hits).toEqual([]);
  });
});
