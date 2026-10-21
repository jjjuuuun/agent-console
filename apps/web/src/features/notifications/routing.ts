import type { NotifyTarget } from "./core";

export interface TargetRoutes {
  /** 대화를 여는 경로(`/<대화 id>`가 이어 붙는다). 없으면 대화 대상은 이동하지 않는다 */
  conversations?: string | undefined;
  runs?: string | undefined;
}

/** 알림 대상 -> 앱 경로. 경로는 라우트 설정 데이터에서 온다. */
export function targetPath(target: NotifyTarget, routes: TargetRoutes): string | undefined {
  if (target.kind === "conversation" && routes.conversations !== undefined) return `${routes.conversations}/${encodeURIComponent(target.conversationId)}`;
  if (target.kind === "run" && routes.runs !== undefined) return `${routes.runs}/${encodeURIComponent(target.runId)}`;
  return undefined;
}

/** 현재 경로가 그 대상을 보여 주는 화면인가. */
export function isViewingTarget(pathname: string, target: NotifyTarget, routes: TargetRoutes): boolean {
  const path = targetPath(target, routes);
  return path !== undefined && (pathname === path || pathname.startsWith(`${path}/`));
}
