import { lazy, Suspense } from "react";
import type { TextEditorProps } from "@agent-console/text-editor";
import { Spinner } from "@agent-console/ui";

// 편집기(CodeMirror)는 크므로 실제로 열 때만 내려받는다. 앱 안의 모든 사용처가 이 한 곳을 거치므로
// text-editor는 정적/동적 import가 섞이지 않고 한 청크로만 나뉜다.
const Editor = lazy(() => import("@agent-console/text-editor").then((m) => ({ default: m.TextEditor })));

export interface LazyTextEditorProps extends TextEditorProps {
  /** 불러오는 동안 스피너에 붙는 접근성 이름. 기본은 `ariaLabel` */
  loadingLabel?: string;
}

/** `@agent-console/text-editor`의 `TextEditor`를 지연 로딩으로 그린다(props 동일). */
export function LazyTextEditor({ loadingLabel, ...props }: LazyTextEditorProps) {
  return (
    <Suspense fallback={<Spinner label={loadingLabel ?? props.ariaLabel} />}>
      <Editor {...props} />
    </Suspense>
  );
}
