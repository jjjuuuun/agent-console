import { createContext, useContext, type ComponentType, type ReactNode } from "react";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";

/** 스키마 `x-ui.widget` 이름 → 위젯. 설정·리소스 폼처럼 서버 스키마를 그리는 곳이 이 표로 앱이 아는 위젯을 꽂는다. */
export type ConfigWidgetTable = Readonly<Record<string, ComponentType<SchemaFormWidgetProps>>>;

const NONE: ConfigWidgetTable = {};
const Ctx = createContext<ConfigWidgetTable>(NONE);

/** 위젯 표를 하위 폼에 공급한다(표는 앱 조립 층 `links/`가 정한다). */
export function ConfigWidgetsProvider({ widgets, children }: { widgets: ConfigWidgetTable; children: ReactNode }) {
  return <Ctx.Provider value={widgets}>{children}</Ctx.Provider>;
}

/** 등록된 위젯 표. 공급자가 없으면 빈 표(이름을 모르는 위젯은 기본 입력으로 그려진다). */
export function useConfigWidgets(): ConfigWidgetTable {
  return useContext(Ctx);
}
