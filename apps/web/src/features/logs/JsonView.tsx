import { lazy, Suspense } from "react";
import { Spinner } from "@agent-console/ui";

// 편집기(CodeMirror)는 크므로 JSON을 실제로 펼칠 때만 내려받는다.
const Editor = lazy(() => import("@agent-console/text-editor").then((m) => ({ default: m.TextEditor })));

export interface JsonViewProps {
  value: unknown;
  /** 접근성 이름 */
  label: string;
  language?: string;
  height?: number;
}

/** 값을 들여 쓴 JSON(문자열이면 그대로)으로 읽기 전용 코드 블록에 그린다. 줄 번호 없는 요약 보기라 높이는 고정이다. */
export function JsonView({ value, label, language = "json", height = 260 }: JsonViewProps) {
  const text = typeof value === "string" ? value : (JSON.stringify(value, null, 2) ?? "");
  return (
    <div className="logs-json" style={{ height }}>
      <Suspense fallback={<Spinner label={label} />}>
        <Editor value={text} language={language} readOnly lineWrap ariaLabel={label} height={height} />
      </Suspense>
    </div>
  );
}
