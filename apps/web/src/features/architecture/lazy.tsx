import { Suspense, lazy, type ComponentProps } from "react";
import { archMessages as t } from "./messages";

const Loaded = lazy(() => import("./ArchitecturePanel").then((m) => ({ default: m.ArchitecturePanel })));

/**
 * 지연 로딩되는 `ArchitecturePanel`. 그림 라이브러리(@xyflow/react)는 구조도 세그먼트를 처음 열 때 내려받는다.
 * 같은 props를 받는다.
 */
export function LazyArchitecturePanel(props: ComponentProps<typeof Loaded>) {
  return (
    <Suspense fallback={<div className="app-loading" role="status" aria-busy="true">{t.status.loading}</div>}>
      <Loaded {...props} />
    </Suspense>
  );
}
