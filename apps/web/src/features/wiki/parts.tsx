/** 위키 화면들이 같이 쓰는 작은 부품: 꺼짐 안내·실패 블록·스켈레톤·검색 칸. 데이터와 콜백은 props. */
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { EmptyState, Icon } from "@agent-console/ui";
import { ErrorBlock } from "../../app/ErrorBlock";
import { useDelayed } from "../../app/useDelayed";
import { isImeKeyEvent } from "../../lib/ime";
import { ROUTE_ROLES, routePath } from "../library";
import { WIKI_LIMITS } from "./wikiConfig";
import { classifyWikiError, failureDetail } from "./wikiErrors";
import { wikiMessages as m } from "./messages";

/** 프로젝트 연동이 꺼져 본문 전체를 대신하는 안내(`wiki.spaces_unavailable`). 기능 모듈 화면으로 가는 링크는 설정이 있을 때만. */
export function UnavailableState() {
  const settings = routePath(ROUTE_ROLES.settings);
  return (
    <div className="wiki-state" data-testid="wiki-unavailable">
      <EmptyState
        icon={<Icon name="folder-off" size={40} />}
        title={m.unavailable.title}
        description={m.unavailable.body}
        action={settings === "/" ? undefined : <a className="app-link-btn" href={`${settings}#modules`}>{m.unavailable.openModules}</a>}
      />
    </div>
  );
}

/** 요청 실패를 종류별로 보인다: 연동 꺼짐은 안내, 위키 없음·폴더 문제·그 밖은 오류 블록(+ 다시 시도). */
export function FailureBlock({ error, title, onRetry, backTo }: { error: unknown; title: string; onRetry?: () => void; backTo?: ReactNode }) {
  const failure = classifyWikiError(error, title);
  if (failure.kind === "unavailable") return <UnavailableState />;
  if (failure.kind === "notFound") return <ErrorBlock title={m.notFound}>{backTo}</ErrorBlock>;
  return <ErrorBlock title={title} message={failureDetail(failure)} {...(onRetry === undefined ? {} : { onRetry, retryLabel: m.retry })} />;
}

/** 150ms 넘게 걸릴 때만 보이는 스켈레톤 행. */
export function ListSkeleton({ rows = 6 }: { rows?: number }) {
  const show = useDelayed(true, WIKI_LIMITS.skeletonDelayMs);
  if (!show) return null;
  return (
    <div className="app-skeleton" role="status" aria-busy="true" aria-label={m.loading}>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="app-skeleton-row" />)}
    </div>
  );
}

export interface DebouncedInputProps {
  value: string;
  /** 입력이 멈춘 뒤(또는 Enter) 새 글을 알린다. 한글 조합 중에는 보내지 않는다. */
  onCommit: (q: string) => void;
  label: string;
  placeholder?: string;
  delayMs?: number;
  className?: string;
  inputRef?: Ref<HTMLInputElement>;
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void;
  onFocus?: () => void;
  onBlur?: () => void;
  /** 접근성 속성(결과 목록을 가리키는 `aria-activedescendant` 등) */
  aria?: Readonly<Record<string, string | boolean | undefined>>;
  /** 입력 역할: 기본 `searchbox`. 결과 목록을 펼치는 입력(`aria-expanded`)은 `combobox`를 준다 */
  role?: "searchbox" | "combobox";
  /** 입력 중 글자가 바뀔 때마다 알림(즉시) */
  onText?: (text: string) => void;
}

/** 입력이 멈춘 뒤 `onCommit`을 부르는 검색 칸. 한글 조합 중에는 보내지 않고, 밖에서 값이 바뀌면 따라간다. */
export function DebouncedInput({ value, onCommit, label, placeholder, delayMs = WIKI_LIMITS.searchDebounceMs, className, inputRef, onKeyDown, onFocus, onBlur, aria, onText, role = "searchbox" }: DebouncedInputProps) {
  const [text, setText] = useState(value);
  const [seen, setSeen] = useState(value);
  const composing = useRef(false);
  if (seen !== value) {
    setSeen(value);
    setText(value);
  }
  const latest = useRef(onCommit);
  useEffect(() => {
    latest.current = onCommit;
  });
  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => {
      if (!composing.current) latest.current(text);
    }, delayMs);
    return () => clearTimeout(timer);
  }, [text, value, delayMs]);
  return (
    <input
      ref={inputRef}
      type="search"
      role={role}
      className={className ?? "wiki-search"}
      aria-label={label}
      placeholder={placeholder ?? label}
      value={text}
      {...(aria as object)}
      onFocus={onFocus}
      onBlur={onBlur}
      onChange={(e) => {
        setText(e.target.value);
        onText?.(e.target.value);
      }}
      onCompositionStart={() => (composing.current = true)}
      onCompositionEnd={(e) => {
        composing.current = false;
        setText(e.currentTarget.value);
      }}
      onKeyDown={(e) => {
        if (isImeKeyEvent(e.nativeEvent)) return;
        onKeyDown?.(e);
        if (!e.defaultPrevented && e.key === "Enter") latest.current(text);
      }}
    />
  );
}
