import type { BackendDescriptor } from "@agent-console/contracts";
import { useBackendReadiness } from "../backendReadiness";
import { ModelCatalogStatus } from "./ModelCatalogStatus";

/**
 * 연결 모달의 카드 아래 모델 줄(`BackendConnectProvider`의 `renderFooter`에 그대로 쓴다).
 * 모델 조회 능력을 선언한 백엔드만 그린다. 로그인 성공·다시 확인으로 그 백엔드의 준비 상태가 새로 오면
 * 목록을 다시 읽는다(서버가 로그인 성공 때 캐시를 비우므로 웹은 다시 GET만 한다).
 */
export function ModelCatalogDialogLine({ backend }: { backend: BackendDescriptor }) {
  const { readiness } = useBackendReadiness();
  if (backend.capabilities?.model_discovery !== true) return null;
  return <ModelCatalogStatus backendId={backend.id} variant="dialog" refetchKey={readiness[backend.id]} />;
}
