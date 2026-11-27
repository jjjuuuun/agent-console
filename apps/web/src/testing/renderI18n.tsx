import { render as baseRender, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { TestI18n } from "./TestI18n";

/** `render`에 한국어 i18n 공급자를 씌운 것(앱 루트 없이 그리는 컴포넌트 테스트용, 앱 코드에서 import하지 않는다). */
export function render(ui: ReactElement, options?: Omit<RenderOptions, "queries">): RenderResult {
  const result = baseRender(<TestI18n>{ui}</TestI18n>, options);
  return { ...result, rerender: (next) => result.rerender(<TestI18n>{next}</TestI18n>) };
}
