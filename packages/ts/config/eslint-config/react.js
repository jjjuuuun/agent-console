import reactHooks from "eslint-plugin-react-hooks";

import { createConfig } from "./index.js";
import agentConsole from "./rules/button-name.js";

/**
 * `createConfig`에 React Hooks 규칙과 `agent-console/button-name`(이름 없는 `<button>` 금지)을 더한다(eslint-plugin-react-hooks 필요).
 * @param {Parameters<typeof createConfig>[0]} [options]
 * @returns {import("eslint").Linter.Config[]}
 */
export function createReactConfig(options) {
  return [
    ...createConfig(options),
    { files: ["**/*.{ts,tsx}"], plugins: { "react-hooks": reactHooks, "agent-console": agentConsole }, rules: { ...reactHooks.configs.recommended.rules, "agent-console/button-name": "error" } },
  ];
}

export default createReactConfig();
