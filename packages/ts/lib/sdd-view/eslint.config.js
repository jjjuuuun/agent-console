import config from "@agent-console/eslint-config/react";

// 사내 의존은 contracts "타입"과 markdown-doc(문서 편집기·칩, design §7R.3)뿐이다. api-client 등은 import하지 않고 props로 받는다.
export default [
  ...config,
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}", "src/testing.ts"],
    rules: {
      "@typescript-eslint/no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@agent-console/*", "!@agent-console/contracts", "!@agent-console/contracts/*", "!@agent-console/markdown-doc"],
              message: "sdd-view는 contracts 타입과 markdown-doc만 import한다. 나머지는 props로 받는다.",
            },
            {
              group: ["@agent-console/contracts", "@agent-console/contracts/*"],
              allowTypeImports: true,
              message: "contracts는 `import type`으로만 가져온다(값 의존 없음).",
            },
          ],
        },
      ],
    },
  },
];
