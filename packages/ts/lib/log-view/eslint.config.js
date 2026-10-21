import config from "@agent-console/eslint-config/react";

// 사내 의존은 contracts "타입"뿐이다(F-19). 다른 사내 패키지(ui·trace-view·schema-form·text-editor 등)는 import하지 않고 슬롯 props로 받는다.
export default [
  ...config,
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@agent-console/*", "!@agent-console/contracts", "!@agent-console/contracts/*"],
              message: "log-view는 contracts 타입만 import한다. 다른 사내 패키지는 슬롯 props로 받는다(F-19).",
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
