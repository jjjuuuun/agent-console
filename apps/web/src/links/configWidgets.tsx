import { lazy, Suspense } from "react";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";
import type { ConfigWidgetTable } from "../app/ConfigWidgets";

// 위젯 본문은 처음 그릴 때 내려받는다(리소스 화면 번들에 메모리 설정 코드가 들어가지 않게).
const ScopeKind = lazy(() => import("../features/memorySettings").then((m) => ({ default: m.ScopeKindWidget })));

function LazyScopeKind(props: SchemaFormWidgetProps) {
  return (
    <Suspense fallback={<input id={props.id} aria-label={props.label} disabled readOnly value={typeof props.value === "string" ? props.value : ""} />}>
      <ScopeKind {...props} />
    </Suspense>
  );
}

/**
 * 스키마 `x-ui.widget` 이름 → 위젯 등록 데이터. 서버 스키마(리소스 종류 `memory`의 접근 설정)가 이 이름을 달면 그 필드를 해당 위젯으로 그린다.
 * 사용자가 다르게 원하면 이 표만 고친다. 이름이 없으면 위젯도 호출도 없다.
 */
export const DEFAULT_CONFIG_WIDGETS: ConfigWidgetTable = {
  "memory-scope-kind": LazyScopeKind,
};
