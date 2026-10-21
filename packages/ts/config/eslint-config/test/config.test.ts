import { expect, test } from "vitest";

import defaults, { DEFAULT_IGNORES, createConfig } from "@agent-console/eslint-config";

test("기본 설정은 dist·node_modules를 제외한다", () => {
  expect(defaults[0]?.ignores).toEqual(DEFAULT_IGNORES);
});

test("globalSets로 전역 변수 집합을 고른다", () => {
  const cfg = createConfig({ globalSets: ["node"] });
  const globalsConfig = cfg.find((c) => c.languageOptions?.globals);
  expect(globalsConfig?.languageOptions?.globals).toHaveProperty("process");
  expect(globalsConfig?.languageOptions?.globals).not.toHaveProperty("document");
});
