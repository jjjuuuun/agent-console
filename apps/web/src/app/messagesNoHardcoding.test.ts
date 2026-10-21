import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DATA_NAMES, dataNameLiteral } from "../testing/dataNames";

/**
 * 한글 문구 표(messages.ts)는 noHardcoding 검사에서 통째로 빠져 있다(카테고리 이름과 우연히 겹칠 수 있어서).
 * 그래도 서버 데이터 이름(연결 종류·리소스 종류·상호작용 종류·사용량 창·모델)이 문구 표의 따옴표 문자열로
 * 들어가면 안 되므로 이 목록만은 문구 표에도 적용한다.
 */

describe("문구 표에도 서버 데이터 이름이 없다", () => {
  const text = readFileSync(resolve(__dirname, "messages.ts"), "utf8");
  it.each(DATA_NAMES)("%s", (name) => {
    expect(dataNameLiteral(name).test(text)).toBe(false);
  });
});
