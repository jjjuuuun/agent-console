import { Icon } from "@agent-console/ui";
import { messages as m } from "../app/messages";
import { MODULE_STATUS } from "./resolve";

const KNOWN: readonly string[] = Object.values(MODULE_STATUS);

/** 상태 칩 글자: 계약이 고정한 5종은 문구 표, 그 밖의 값은 원문 그대로. */
export function moduleStatusLabel(status: string): string {
  return (m.moduleStatus as Record<string, string>)[status] ?? status;
}

/**
 * 모듈 상태 칩(색 + 아이콘 + 글자, 색 단독 금지). 모르는 상태는 중립 칩 + 값 그대로.
 * 색은 `data-module-status`로 정하고 토큰만 쓴다(app.css).
 */
export function ModuleStatusChip({ status }: { status: string }) {
  const known = KNOWN.includes(status);
  return (
    <span className="app-module-chip" data-module-status={known ? status : "unknown"}>
      <Icon name={known ? `module-${status}` : "module-disabled"} size={12} />
      <span>{moduleStatusLabel(status)}</span>
    </span>
  );
}
