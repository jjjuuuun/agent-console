import { createReactConfig } from "./packages/ts/config/eslint-config/react.js";

// 저장소 루트(앱·스크립트·E2E)용 설정. 패키지는 각자 eslint.config.js를 가진다(ESLint 10은 파일 위치 기준으로 설정을 찾는다).
export default [
  ...createReactConfig({
    ignores: ["**/playwright-report/**", "**/test-results/**", "packages/py/**", "apps/server/**", "apps/cli/**", "**/.venv/**"],
  }),
  {
    // E2E는 서버 응답(JSON)을 느슨하게 다룬다.
    files: ["apps/web/e2e/**/*.ts"],
    rules: { "@typescript-eslint/no-explicit-any": "off" },
  },
];
