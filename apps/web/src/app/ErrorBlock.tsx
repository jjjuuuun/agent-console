import type { ReactNode } from "react";
import { Button, Spinner } from "@agent-console/ui";
import type { Fix } from "@agent-console/contracts";
import type { ErrorView } from "./errors";
import { FixButtons } from "./fix";

export interface ErrorBlockProps {
  title: string;
  /** 서버 message 한 줄 등 */
  message?: string;
  /** 접힌 "상세"에 들어갈 정보(code 등). 토큰은 절대 넣지 않는다 */
  details?: string;
  detailsLabel?: string;
  retryLabel?: string;
  onRetry?: () => void;
  /** 해결 버튼(오류 데이터 `fix`). 역할을 맡은 화면이 없으면 그 버튼은 숨는다 */
  fix?: Fix | null | undefined;
  /** 보조 버튼(예: 새로고침) */
  secondary?: { label: string; onClick: () => void };
  children?: ReactNode;
}

/** 영역 전체를 대신하는 에러 블록. */
export function ErrorBlock({ title, message, details, detailsLabel = "상세", retryLabel, onRetry, fix, secondary, children }: ErrorBlockProps) {
  return (
    <div className="app-error-block" role="alert">
      <h2 className="app-block-title">{title}</h2>
      {message === undefined ? null : <p className="ac-text app-wrap">{message}</p>}
      {children}
      <FixButtons fix={fix} />
      {onRetry === undefined ? null : (
        <Button variant="primary" onClick={onRetry}>
          {retryLabel ?? "다시 시도"}
        </Button>
      )}
      {secondary === undefined ? null : <Button onClick={secondary.onClick}>{secondary.label}</Button>}
      {details === undefined || details === "" ? null : (
        <details className="app-details">
          <summary>{detailsLabel}</summary>
          <pre className="ac-pre">{details}</pre>
        </details>
      )}
    </div>
  );
}

/** `ErrorView`에서 상세 문자열을 만든다. */
export function errorDetails(view: ErrorView, extra?: string): string {
  return [extra, view.code === undefined ? undefined : `code: ${view.code}`, view.status ? `status: ${view.status}` : undefined]
    .filter((x): x is string => x !== undefined && x !== "")
    .join("\n");
}

/** 데이터 로딩 중 표시(스크린리더용 status 포함). */
export function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="app-loading" role="status" aria-busy="true">
      <Spinner />
      <span>{label}</span>
    </div>
  );
}
