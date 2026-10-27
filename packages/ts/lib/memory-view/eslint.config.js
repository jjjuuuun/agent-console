import config from "@agent-console/eslint-config/react";

// 사내 의존은 contracts "타입"과 text-editor뿐이다(design §5.7R.2). api-client·log-view·ui 등은 import하지 않고 props로 받는다.
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
              group: ["@agent-console/*", "!@agent-console/contracts", "!@agent-console/contracts/*", "!@agent-console/text-editor"],
              message: "memory-view는 contracts 타입과 text-editor만 import한다. 나머지는 props로 받는다.",
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
