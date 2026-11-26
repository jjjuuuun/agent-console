import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { idProblem, isReservedId } from "./ids";

describe("예약어 id 검사(서버가 준 목록)", () => {
  it("대소문자·공백을 무시하고, 목록이 없으면 통과하며, 앞선 문제가 우선이다", () => {
    expect(idProblem("Zed-Word", new Set(), ["zed-word"])).toBe("reserved");
    expect(idProblem("zed-word", new Set())).toBeUndefined();
    expect(idProblem("zed-word", new Set(["zed-word"]), ["zed-word"])).toBe("duplicate");
    expect(idProblem("a b", new Set(), ["a b"])).toBe("pattern");
    expect(isReservedId("", [""])).toBe(false);
    expect(isReservedId(" ZED ", ["zed"])).toBe(true);
  });
});

/** R0: 웹 소스(테스트 제외)에는 서버가 주는 예약어 문자열이 없어야 한다. */
describe("웹 소스에 예약어 리터럴 없음", () => {
  const FORBIDDEN = ["variables", "check"];
  const root = join(__dirname, "..", "..");
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) && !full.replaceAll("\\", "/").includes("/sdd/widgets/") && /(features\/(library|sdd|projects))/.test(full.replaceAll("\\", "/"))) files.push(full);
    }
  };
  walk(root);
  it("예약어로 알려진 말이 따옴표 문자열로 쓰이지 않는다(문구 표·sdd·library·projects)", () => {
    const offenders = files.filter((f) => FORBIDDEN.some((w) => new RegExp(`["'\`]${w}["'\`]`).test(readFileSync(f, "utf-8"))));
    expect(offenders).toEqual([]);
  });
});
