import { TextEditor, type TextEditorHandle, type TextEditorStatus } from "@agent-console/text-editor";
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { formatBytes, languageForContentType, utf8Bytes } from "./format";
import { formatMessage, resolveMessages } from "./messages";

/** 저장 상태 표시. `pending`은 조합 중 저장 요청을 미뤄 둔 상태(편집기 안에서 계산). */
export type EntrySaveState = "saved" | "dirty" | "saving" | "failed";

/** 편집기가 밖으로 여는 명령. 머리의 [저장] 단추도 같은 경로로 부르면 조합 중 보류 규칙이 같이 적용된다. */
export interface MemoryEntryEditorHandle {
  /** 저장 요청. 조합 중이면 미루고 조합이 끝나면 한 번 저장한다. 한도 초과·읽기 전용이면 아무것도 하지 않는다. */
  requestSave: () => void;
  isComposing: () => boolean;
}

/** 편집기 자리에 다른 입력을 꽂는 슬롯(기본은 text-editor). 테스트·다른 편집기용. */
export interface EditorSlotProps {
  value: string;
  onChange: (value: string) => void;
  language: string;
  readOnly: boolean;
  ariaLabel: string;
  lineWrap: boolean;
  onSave: () => void;
  onCompositionChange: (composing: boolean) => void;
  onStatus: (status: TextEditorStatus) => void;
}

export interface MemoryEntryEditorProps {
  /** 본문(제어형). */
  value: string;
  onChange: (value: string) => void;
  /** 항목 키(접근 이름 "{키} 본문"). */
  entryKey: string;
  /** 본문 형식(열린 문자열). 편집기 언어를 정한다. */
  contentType?: string | null;
  /** 저장 요청: Ctrl+S, 또는 핸들의 `requestSave`. 조합 중에는 호출되지 않고 조합이 끝난 뒤 한 번 호출된다. */
  onSave: () => void;
  /** 저장 상태(머리 텍스트와 같은 값). 조합 중 보류가 있으면 "저장 대기…"로 덮어 보인다. */
  saveState?: EntrySaveState;
  readOnly?: boolean;
  /** 설치자 한도(UTF-8 바이트). 모르면 생략: 한도 계산·저장 막기가 없다(서버 422가 최종). */
  maxBytes?: number | null;
  lineWrap?: boolean;
  /** 조합 상태가 바뀔 때 알린다(앱이 검사를 미루는 데 쓴다). */
  onCompositionChange?: (composing: boolean) => void;
  /** 저장 보류 상태가 바뀔 때 알린다. */
  onSavePendingChange?: (pending: boolean) => void;
  handleRef?: Ref<MemoryEntryEditorHandle>;
  /** 편집기 슬롯. 생략하면 text-editor의 `TextEditor`. */
  renderEditor?: (props: EditorSlotProps) => ReactNode;
  /** 상태 줄 오른쪽에 더할 조각. */
  statusExtra?: ReactNode;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 메모리 본문 편집기. text-editor를 그대로 쓰고(자체 편집 UI 없음) 그 위에 다음을 더한다.
 * - IME: 조합 중에는 Ctrl+S와 저장 요청을 미뤘다가 조합이 끝나면 한 번 저장한다. 조합 중에는 바이트·한도 계산을 멈춘다(마지막 값 유지).
 * - 한도: UTF-8 바이트가 `maxBytes`를 넘으면 편집은 되지만 저장이 막히고 상태 줄이 위험 표시(색 + 아이콘 + 글자)가 된다.
 * - 상태 줄: 줄·열 / 바이트·한도 / 형식 / 저장 상태.
 */
export function MemoryEntryEditor({
  value, onChange, entryKey, contentType, onSave, saveState = "saved", readOnly = false, maxBytes = null, lineWrap = true, onCompositionChange,
  onSavePendingChange, handleRef, renderEditor, statusExtra, messages: custom, className,
}: MemoryEntryEditorProps) {
  const m = resolveMessages(custom);
  const [composing, setComposing] = useState(false);
  const [pending, setPending] = useState(false);
  const [position, setPosition] = useState<{ line: number; col: number }>({ line: 1, col: 1 });
  const editorHandle = useRef<TextEditorHandle>(null);
  const composingRef = useRef(false);
  const pendingRef = useRef(false);

  // 바이트 계산은 조합 중에는 멈춘다(마지막 값 유지). 조합이 끝나면 다시 계산한다.
  const [measured, setMeasured] = useState(() => utf8Bytes(value));
  if (!composing) {
    const bytes = utf8Bytes(value);
    if (bytes !== measured) setMeasured(bytes);
  }
  const limit = maxBytes ?? null;
  const overBy = limit !== null ? Math.max(0, measured - limit) : 0;
  const overLimit = overBy > 0;
  const blocked = readOnly || overLimit;

  const latest = useRef({ onSave, blocked, onSavePendingChange, onCompositionChange });
  useEffect(() => {
    latest.current = { onSave, blocked, onSavePendingChange, onCompositionChange };
  });

  const setPendingBoth = useCallback((next: boolean) => {
    if (pendingRef.current === next) return;
    pendingRef.current = next;
    setPending(next);
    latest.current.onSavePendingChange?.(next);
  }, []);
  const requestSave = useCallback(() => {
    if (latest.current.blocked) return;
    if (composingRef.current) {
      setPendingBoth(true);
      return;
    }
    latest.current.onSave();
  }, [setPendingBoth]);
  useImperativeHandle(handleRef, () => ({ requestSave, isComposing: () => composingRef.current }), [requestSave]);

  // 조합이 끝나면 미뤄 둔 저장을 한 번 한다(effect라 마지막 onChange가 반영된 뒤).
  useEffect(() => {
    if (!composing && pending) {
      setPendingBoth(false);
      if (!latest.current.blocked) latest.current.onSave();
    }
  }, [composing, pending, setPendingBoth]);

  const handleComposition = useCallback((next: boolean) => {
    composingRef.current = next;
    setComposing(next);
    latest.current.onCompositionChange?.(next);
  }, []);
  const handleStatus = useCallback((s: TextEditorStatus) => setPosition({ line: s.line, col: s.col }), []);

  // 조합 중 Ctrl+S: text-editor는 무시하므로 여기서 가로채 보류로 바꾼다(브라우저 저장 대화상자도 막는다).
  const onKeyDownCapture = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s" && composingRef.current) {
      e.preventDefault();
      requestSave();
    }
  };

  const language = useMemo(() => languageForContentType(contentType), [contentType]);
  const ariaLabel = formatMessage(m["editor.aria"] as string, { key: entryKey });
  const slotProps: EditorSlotProps = { value, onChange, language, readOnly, ariaLabel, lineWrap, onSave: requestSave, onCompositionChange: handleComposition, onStatus: handleStatus };

  const shownState: EntrySaveState | "pending" = pending ? "pending" : saveState;
  const bytesText = limit !== null
    ? formatMessage(m["editor.bytes"] as string, { used: formatBytes(measured, m), limit: formatBytes(limit, m) })
    : formatMessage(m["editor.bytesNoLimit"] as string, { used: formatBytes(measured, m) });

  return (
    <div className={`ac-mem-root ac-mem-editor${className ? ` ${className}` : ""}`} onKeyDownCapture={onKeyDownCapture}>
      <div className="ac-mem-editor-body">
        {renderEditor ? <SlotHost render={renderEditor} slot={slotProps} /> : (
          <TextEditor value={value} onChange={onChange} language={language} readOnly={readOnly} lineWrap={lineWrap} ariaLabel={ariaLabel} onSave={requestSave}
            onCompositionChange={handleComposition} onStatus={handleStatus} handleRef={editorHandle} height="fill" />
        )}
      </div>
      <div className="ac-mem-editor-status" role="group" aria-label={m["editor.status"]}>
        <span className="ac-mem-num">{formatMessage(m["editor.position"] as string, { line: position.line, col: position.col })}</span>
        <span className="ac-mem-num" data-danger={overLimit ? "" : undefined}>
          {overLimit ? <span className="ac-mem-icon ac-mem-icon-failed" aria-hidden="true" /> : null}
          {bytesText}
          {overLimit ? <> · {formatMessage(m["editor.overLimit"] as string, { over: formatBytes(overBy, m) })}</> : null}
        </span>
        {contentType ? <span className="ac-mem-mono">{contentType}</span> : null}
        <span className="ac-mem-editor-save" role="status" data-state={shownState}>{m[`save.${shownState}`]}</span>
        {statusExtra}
      </div>
    </div>
  );
}

/** 슬롯 함수를 자식 컴포넌트 안에서 부른다(렌더 함수가 부모의 ref를 닫고 있어도 부모 렌더와 섞이지 않게). */
function SlotHost({ render, slot }: { render: (props: EditorSlotProps) => ReactNode; slot: EditorSlotProps }) {
  return <>{render(slot)}</>;
}
