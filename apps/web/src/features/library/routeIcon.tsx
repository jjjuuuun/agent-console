import { Icon } from "@agent-console/ui";
import { DEFAULT_ROUTES, routeServing } from "../../shell/routeConfig";

/**
 * 역할을 맡은 라우트의 아이콘(빈 상태 스팟·아이콘 타일용). 이름은 라우트 설정 데이터의 `emptyIcon`(없으면 `icon`)이다.
 * 맡은 라우트가 없으면 null이라 타일이 그려지지 않는다.
 */
export function routeIconNode(role: string, size = 24) {
  const route = routeServing(DEFAULT_ROUTES, role);
  const name = route?.emptyIcon ?? route?.icon;
  return name === undefined ? null : <Icon name={name} size={size} />;
}
