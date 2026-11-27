/**
 * 앱 공급자 없이 컴포넌트 하나만 그리는 테스트용 i18n 공급자. 한국어(기본)·영어 앱 묶음을 모두 올려 둔다(첫 청크 지연 없이 동기).
 * 앱 전체를 올리는 `mountApp`에는 필요 없다.
 */
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createI18n, type MessageTree } from "@agent-console/i18n";
import { AppI18nProvider } from "../i18n";

const files = import.meta.glob<MessageTree>("../locales/*/*.json", { eager: true, import: "default" });
const FILE = /locales\/([^/]+)\/([^/]+)\.json$/;

/** 모든 앱 묶음(언어 → 네임스페이스 → 문구)으로 만든 i18n 인스턴스. */
export function createTestAppI18n(language = "ko") {
  const bundled: Record<string, Record<string, MessageTree>> = {};
  for (const [path, tree] of Object.entries(files)) {
    const hit = FILE.exec(path);
    if (hit) (bundled[hit[1]!] ??= {})[hit[2]!] = tree;
  }
  return createI18n({ language, bundled });
}

const shared = createTestAppI18n();

export function TestI18n({ children }: { children: ReactNode }) {
  return <AppI18nProvider i18n={shared}>{children}</AppI18nProvider>;
}

/** `render`에 `TestI18n`을 감싼다(다시 그리기에도 유지). */
export function renderWithI18n(ui: ReactElement, options: Omit<RenderOptions, "wrapper"> = {}): RenderResult {
  return render(ui, { ...options, wrapper: TestI18n });
}
