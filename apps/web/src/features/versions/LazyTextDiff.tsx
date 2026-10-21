import { lazy, Suspense } from "react";
import type { TextDiffProps } from "@agent-console/text-editor";
import { Spinner } from "@agent-console/ui";

// CodeMirror 병합 보기는 크므로 실제로 펼칠 때만 내려받는다(LazyTextEditor와 같은 청크로 묶인다).
const Diff = lazy(() => import("@agent-console/text-editor").then((m) => ({ default: m.TextDiff })));

/** `@agent-console/text-editor`의 `TextDiff`를 지연 로딩으로 그린다(props 동일). */
export function LazyTextDiff(props: TextDiffProps) {
  return (
    <Suspense fallback={<Spinner label={props.ariaLabel} />}>
      <Diff {...props} />
    </Suspense>
  );
}
