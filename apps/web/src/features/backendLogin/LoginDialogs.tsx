import { useEffect, useRef, useState, type FormEvent } from "react";
import type { BackendLoginSession, BackendLogoutResult, LoginMethodInfo } from "@agent-console/contracts";
import { Banner, Button, Dialog, Spinner } from "@agent-console/ui";
import { FixButtons } from "../../app/fix";
import "./backendLogin.css";
import { loginMessages as t } from "./messages";
import { formatRemaining, isOpenableUrl, isTerminalPhase } from "./types";

/* 표현 컴포넌트: 데이터와 콜백만 받는다. 서버·쿼리를 모른다. */

export interface LoginConfirmDialogProps {
  open: boolean;
  /** 대화상자 제목(로그인 방법 라벨, 서버 데이터) */
  title: string;
  method: Pick<LoginMethodInfo, "description" | "notice" | "writes"> | undefined;
  starting: boolean;
  error?: string | undefined;
  onCancel: () => void;
  onStart: () => void;
}

/** ① 시작 확인: notice와 쓰기 범위가 늘 보인다(숨기기 없음). 기본 포커스는 [로그인 시작]. */
export function LoginConfirmDialog({ open, title, method, starting, error, onCancel, onStart }: LoginConfirmDialogProps) {
  const startRef = useRef<HTMLButtonElement>(null);
  const writes = method?.writes ?? [];
  return (
    <Dialog
      open={open}
      size="md"
      title={title}
      onClose={onCancel}
      initialFocus={startRef}
      actions={
        <>
          <Button onClick={onCancel}>{t.cancel}</Button>
          <Button ref={startRef} variant="primary" disabled={starting} onClick={onStart}>
            {starting ? t.starting : t.start}
          </Button>
        </>
      }
    >
      {method?.description ? <p className="ac-text">{method.description}</p> : null}
      {method?.notice ? (
        <Banner tone="warning" title={t.noticeHeading}>
          <span data-testid="login-notice">{method.notice}</span>
        </Banner>
      ) : null}
      {writes.length > 0 ? (
        <section aria-label={t.writesHeading}>
          <h3 className="app-block-title">{t.writesHeading}</h3>
          <ul data-testid="login-writes">
            {writes.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <div aria-live="polite">{error ? <Banner tone="danger">{error}</Banner> : null}</div>
    </Dialog>
  );
}

export interface LoginBusyDialogProps {
  open: boolean;
  title: string;
  busy: boolean;
  onResume: () => void;
  onCancelOther: () => void;
  onClose: () => void;
}

/** 다른 창에서 이미 로그인 중(409). */
export function LoginBusyDialog({ open, title, busy, onResume, onCancelOther, onClose }: LoginBusyDialogProps) {
  const resumeRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open={open}
      size="sm"
      title={title}
      onClose={onClose}
      initialFocus={resumeRef}
      actions={
        <>
          <Button onClick={onClose}>{t.close}</Button>
          <Button disabled={busy} onClick={onCancelOther}>{t.busyCancelOther}</Button>
          <Button ref={resumeRef} variant="primary" disabled={busy} onClick={onResume}>{t.busyResume}</Button>
        </>
      }
    >
      <p role="status" className="ac-text"><strong>{t.busyTitle}</strong></p>
      <p className="ac-text">{t.busyBody}</p>
    </Dialog>
  );
}

/** 글자를 보내는 작은 폼. 값은 보낸 뒤 바로 비우고 어디에도 남기지 않는다. */
function SecretSendForm({ label, submitLabel, sending, onSend, inputRef }: { label: string; submitLabel: string; sending: boolean; onSend: (text: string) => void; inputRef?: React.RefObject<HTMLInputElement | null> }) {
  const [value, setValue] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = value;
    if (text === "") return;
    setValue("");
    onSend(text);
  };
  return (
    <form className="app-login-code" onSubmit={submit}>
      <label>
        <span className="app-muted">{label}</span>
        <input ref={inputRef} className="ac-input" type="password" autoComplete="off" spellCheck={false} value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <Button type="submit" disabled={sending || value === ""}>{sending ? t.codeSending : submitLabel}</Button>
    </form>
  );
}

export interface LoginSessionDialogProps {
  open: boolean;
  title: string;
  session: BackendLoginSession;
  /** 현재 시각(ms). 남은 시간 계산용 */
  nowMs: number;
  /** 글자 보내기 요청 중 */
  sending: boolean;
  /** 마지막 보내기 실패 문장(값은 포함하지 않는다) */
  sendError?: string | undefined;
  method?: Pick<LoginMethodInfo, "notice"> | undefined;
  onSendText: (text: string) => void;
  onSendKey: (key: string) => void;
  /** 진행 중에는 취소, 끝났으면 닫기 */
  onCancel: () => void;
  onClose: () => void;
  onRetry: () => void;
}

function stepStates(session: BackendLoginSession): ("done" | "active" | "todo")[] {
  if (session.phase === "succeeded") return ["done", "done", "done"];
  if (session.phase === "verifying") return ["done", "done", "active"];
  if (session.needs_code) return ["done", "active", "todo"];
  return ["active", "todo", "todo"];
}

/** ② 진행·결과 대화상자. 단계 3개, 열기/복사, 코드 칸, 접힌 CLI 화면, 취소, 성공·실패·시간 초과. */
export function LoginSessionDialog({ open, title, session, nowMs, sending, sendError, method, onSendText, onSendKey, onCancel, onClose, onRetry }: LoginSessionDialogProps) {
  const terminal = isTerminalPhase(session.phase);
  const states = stepStates(session);
  const closeRef = useRef<HTMLButtonElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState(false);
  const needsCode = session.needs_code === true;
  useEffect(() => {
    if (needsCode && !terminal) codeRef.current?.focus();
  }, [needsCode, terminal]);
  const url = isOpenableUrl(session.open_url) ? session.open_url : null;
  const copy = () => {
    void navigator.clipboard?.writeText(url ?? "").then(() => setCopied(true), () => undefined);
  };
  const failed = session.phase === "failed" || session.phase === "expired";
  const detailRows = Object.entries(session.details ?? {});
  const screen = session.screen ?? [];
  const keys = session.accepts_keys ?? [];
  return (
    <Dialog
      open={open}
      size="md"
      title={title}
      onClose={terminal ? onClose : onCancel}
      {...(session.phase === "succeeded" ? { initialFocus: closeRef } : {})}
      actions={
        terminal ? (
          <>
            {failed ? <Button variant="primary" onClick={onRetry}>{t.retry}</Button> : null}
            <Button ref={closeRef} variant={failed ? "secondary" : "primary"} onClick={onClose}>{t.close}</Button>
          </>
        ) : (
          <Button onClick={onCancel}>{t.cancel}</Button>
        )
      }
    >
      {!terminal ? <p className="app-muted" data-testid="login-remaining">{t.remaining(formatRemaining(session.expires_at, nowMs))}</p> : null}
      {method?.notice ? <p className="app-muted">{method.notice}</p> : null}
      {(session.warnings ?? []).length > 0 ? (
        <Banner tone="warning">
          <ul>{(session.warnings ?? []).map((w) => <li key={w}>{w}</li>)}</ul>
        </Banner>
      ) : null}
      <div aria-live="polite" data-testid="login-message">
        {session.phase === "cancelled" ? <p className="ac-text">{t.cancelled}</p> : session.message ? <p className="ac-text"><strong>{session.message}</strong></p> : null}
      </div>
      {session.phase !== "cancelled" && !failed ? (
        <ol className="app-login-steps" aria-label={t.stepsLabel}>
          {t.steps.map((label, i) => (
            <li key={label} data-state={states[i]}>
              <span>{label}</span> <span className="app-muted">{states[i] === undefined ? "" : t.stepState[states[i]]}</span>
              {i === 0 && !terminal && url ? (
                <div className="app-login-open">
                  <p className="app-muted">{t.browserHint}</p>
                  <a className="ac-btn" data-variant="primary" data-size="md" href={url} target="_blank" rel="noopener noreferrer">{t.openPage}</a>{" "}
                  <Button size="sm" onClick={copy}>{t.copyLink}</Button>
                  <span role="status" className="app-muted">{copied ? t.linkCopied : ""}</span>
                </div>
              ) : null}
              {i === 1 && !terminal && needsCode ? (
                <SecretSendForm label={session.code_label || t.codeLabelFallback} submitLabel={t.codeSend} sending={sending} onSend={onSendText} inputRef={codeRef} />
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
      <div role="alert">{sendError ? <Banner tone="danger">{sendError}</Banner> : null}</div>
      {failed ? <FixButtons fix={{ actions: session.fixes ?? [] }} /> : null}
      {(failed && (session.reason || detailRows.length > 0)) || screen.length > 0 || !terminal ? (
        <details className="app-details">
          <summary>{failed ? t.details : t.screenToggle}</summary>
          {failed && session.reason ? <p className="app-muted">{t.reasonLabel}: {session.reason}</p> : null}
          {detailRows.map(([k, v]) => <p key={k} className="app-muted">{k}: {typeof v === "string" ? v : JSON.stringify(v)}</p>)}
          <pre className="app-login-screen" aria-label={t.screenLabel} tabIndex={0}>{screen.length > 0 ? screen.join("\n") : t.screenEmpty}</pre>
          {!terminal ? (
            <>
              <SecretSendForm label={t.screenSendLabel} submitLabel={t.screenSend} sending={sending} onSend={onSendText} />
              {keys.map((k) => (
                <Button key={k} size="sm" disabled={sending} onClick={() => onSendKey(k)}>{t.keyButton(t.keyLabels[k] ?? k)}</Button>
              ))}
            </>
          ) : null}
        </details>
      ) : null}
      {session.phase === "verifying" ? <Spinner /> : null}
    </Dialog>
  );
}

export interface LogoutDialogProps {
  open: boolean;
  title: string;
  running: boolean;
  result: BackendLogoutResult | null;
  error?: string | undefined;
  onCancel: () => void;
  onConfirm: () => void;
  onClose: () => void;
}

/** 로그아웃 확인 → 결과. 터미널의 Claude Code도 로그아웃된다는 사실을 알린다. */
export function LogoutDialog({ open, title, running, result, error, onCancel, onConfirm, onClose }: LogoutDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const done = result !== null;
  return (
    <Dialog
      open={open}
      size="sm"
      title={title}
      onClose={done ? onClose : onCancel}
      initialFocus={cancelRef}
      actions={
        done ? (
          <Button ref={cancelRef} variant="primary" onClick={onClose}>{t.close}</Button>
        ) : (
          <>
            <Button ref={cancelRef} onClick={onCancel}>{t.cancel}</Button>
            <Button variant="danger" disabled={running} onClick={onConfirm}>{running ? t.logoutRunning : t.logoutConfirm}</Button>
          </>
        )
      }
    >
      {done ? (
        <div aria-live="polite">
          <p className="ac-text">{result.message || (result.ok ? t.logoutDone : t.logoutFailed)}</p>
          {!result.ok ? <FixButtons fix={{ actions: result.fixes ?? [] }} /> : null}
        </div>
      ) : (
        <p className="ac-text">{t.logoutBody}</p>
      )}
      <div role="alert">{error ? <Banner tone="danger">{error}</Banner> : null}</div>
    </Dialog>
  );
}
