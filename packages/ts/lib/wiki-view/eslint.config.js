import config from "@agent-console/eslint-config/react";

// 사내 의존은 contracts(타입 + 상수 전용 진입점)·markdown-doc·text-editor뿐이다(design §7R.3). api-client 등은 import하지 않고 props로 받는다.
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
              group: [
                "@agent-console/*",
                "!@agent-console/contracts",
                "!@agent-console/contracts/*",
                "!@agent-console/markdown-doc",
                "!@agent-console/text-editor",
              ],
              message: "wiki-view는 contracts·markdown-doc·text-editor만 import한다. 나머지(api-client 등)는 props로 받는다.",
            },
            {
              regex: "^@agent-console/contracts($|/(?!constants$))",
              allowTypeImports: true,
              message: "contracts는 `import type`으로만 가져온다. 값은 상수 전용 진입점 `@agent-console/contracts/constants`에서만.",
            },
          ],
        },
      ],
    },
  },
];
