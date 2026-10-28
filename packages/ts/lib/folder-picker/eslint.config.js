import config from "@agent-console/eslint-config/react";

// 사내 패키지(api-client 등)는 import하지 않는다. 서버 연결은 check·list·createFolder 콜백 props로 받는다.
export default [
  ...config,
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-restricted-imports": [
        "error",
        { patterns: [{ group: ["@agent-console/*"], message: "folder-picker는 다른 사내 패키지를 import하지 않는다. 연결은 props로 받는다." }] },
      ],
    },
  },
];
