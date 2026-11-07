import { expect, test } from "vitest";

// README "최소 사용"의 ```ts readme 블록과 아래 표시 구간이 같아야 한다(`pnpm pkg-lint`가 검사).
// readme:start
import { builtinWidgets, createWidgetRegistry } from "@agent-console/log-view";
import { cellRenderers, configWidgets, gaugeWidget } from "@agent-console/example-web";

const registry = createWidgetRegistry(builtinWidgets, [gaugeWidget]);
const gaugeRegistered = registry.has("example.gauge");
const cellViews = Object.keys(cellRenderers);
const widgetNames = Object.keys(configWidgets);
// readme:end

test("README 예제가 실제로 돈다", () => {
  expect(gaugeRegistered).toBe(true);
  expect(cellViews).toEqual(["example-badge"]);
  expect(widgetNames).toEqual(["example.tags"]);
});
