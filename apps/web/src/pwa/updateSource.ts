import type { UpdateSource } from "./PwaContext";

export interface UpdateSourceDeps {
  /** 서비스 워커 등록기(`virtual:pwa-register`의 `registerSW` 모양). 대기 상태가 되면 `onNeedRefresh`를 부른다 */
  register: (hooks: { onNeedRefresh: () => void }) => (reloadPage?: boolean) => Promise<void>;
  /**
   * 이 페이지를 지금 제어하는 서비스 워커가 있는가.
   * 제어하는 워커가 없는 상태의 대기는 "최초 설치"라서 갱신이 아니다(바꿔치울 옛 버전이 없다).
   */
  hasController: () => boolean;
}

/**
 * 서비스 워커의 "새 버전 대기"를 `UpdateSource`로 바꾼다. 최초 설치(제어하는 워커 없음)는 갱신으로 알리지 않는다.
 * 자동 새로고침은 하지 않는다(작성 중 데이터 보호): 적용은 `apply()`를 부를 때만.
 */
export function createUpdateSource({ register, hasController }: UpdateSourceDeps): UpdateSource {
  let waiting = false;
  const listeners = new Set<() => void>();
  const updateSW = register({
    onNeedRefresh() {
      if (!hasController()) return;
      waiting = true;
      listeners.forEach((l) => l());
    },
  });
  return {
    getSnapshot: () => waiting,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    apply: () => void updateSW(true),
  };
}
