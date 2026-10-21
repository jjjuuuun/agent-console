import { EmptyState, Icon, PageHeader } from "@agent-console/ui";
import { lookupMessage, messages as m } from "../app/messages";
import type { RouteDef } from "./routeConfig";

/**
 * 아직 구현되지 않은 화면 자리. 라우트 설정 데이터만으로 제목·아이콘을 그린다.
 * 실제 화면이 들어오면 `routes.tsx`의 페이지 표에서 이 자리를 바꾼다.
 */
export function PlaceholderScreen({ route, detail }: { route: RouteDef; detail?: string }) {
  const title = lookupMessage(route.titleKey);
  return (
    <div className="app-screen-frame" data-screen={route.id} data-placeholder="true">
      <PageHeader title={title} />
      <div className="app-screen-body">
        <EmptyState icon={<Icon name={route.icon} size={24} />} title={title} description={detail === undefined ? m.placeholder.body : `${m.placeholder.body} (${detail})`} secondaryAction={<span className="app-muted">{m.placeholder.hint}</span>} />
      </div>
    </div>
  );
}
