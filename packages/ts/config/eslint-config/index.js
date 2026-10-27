import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

/** 어느 패키지에서나 린트하지 않는 경로. */
export const DEFAULT_IGNORES = ["**/dist/**", "**/dist-*/**", "**/node_modules/**", "**/coverage/**", "**/*.generated.*"];

/**
 * ESLint flat config(배열)를 만든다.
 * @param {{ignores?: string[], globalSets?: string[]}} [options] ignores: 추가로 제외할 glob, globalSets: `globals` 패키지의 집합 이름(기본 node·browser)
 * @returns {import("eslint").Linter.Config[]}
 */
export function createConfig({ ignores = [], globalSets = ["node", "browser"] } = {}) {
  return tseslint.config(
    { ignores: [...DEFAULT_IGNORES, ...ignores] },
    js.configs.recommended,
    ...tseslint.configs.recommended,
    {
      files: ["**/*.{ts,tsx,cjs,js,mjs}"],
      languageOptions: { globals: Object.assign({}, ...globalSets.map((s) => globals[s])) },
    },
  );
}

export default createConfig();
