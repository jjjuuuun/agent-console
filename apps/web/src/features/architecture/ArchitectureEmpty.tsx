import { Button, EmptyState, Icon } from "@agent-console/ui";
import type { ArchErrorInfo } from "./archLib";
import { archMessages as t } from "./messages";

export interface ArchitectureEmptyProps {
  /** 오류 분류(§8의 A 규칙 없음 · D 상한 초과 · E 요청 오류 · F 프로필 오류) */
  error: ArchErrorInfo;
  onRetry?: () => void;
  /** [설정 열기]·[설정에서 고치기]. 없으면 버튼이 없다(설정 섹션이 없는 서버). */
  onOpenSettings?: () => void;
  /** [필터 열기](상한 초과). */
  onFocusFilters?: () => void;
}

/** 그림 자리를 대신하는 블록(§8 A·D·E·F). B(이벤트 없음)·C(모두 수집 안 됨)는 그림을 그대로 두므로 `ArchitectureNotice`가 맡는다. */
export function ArchitectureEmpty({ error, onRetry, onOpenSettings, onFocusFilters }: ArchitectureEmptyProps) {
  const icon = <Icon name="architecture" size={32} />;
  const button = (label: string, onClick: (() => void) | undefined, primary = false) =>
    onClick === undefined ? undefined : <Button variant={primary ? "primary" : undefined} onClick={onClick}>{label}</Button>;
  let block: { title: string; body: string; action: React.ReactNode };
  switch (error.kind) {
    case "rules":
      block = { title: t.empty.rules.title, body: t.empty.rules.body, action: button(t.empty.rules.action, onOpenSettings) };
      break;
    case "tooBig":
      block = { title: t.empty.tooBig.title, body: t.empty.tooBig.body(error.events, error.limit), action: button(t.empty.tooBig.action, onFocusFilters) };
      break;
    case "profile":
      block = { title: t.empty.profileError.title, body: error.message, action: button(t.empty.profileError.action, onOpenSettings) };
      break;
    default:
      block = { title: t.empty.error.title, body: error.message, action: button(t.empty.error.action, onRetry, true) };
  }
  return (
    <div className="arch-empty" role={error.kind === "error" || error.kind === "profile" ? "alert" : "status"} data-kind={error.kind}>
      <EmptyState icon={icon} title={block.title} description={block.body} action={block.action} />
    </div>
  );
}
