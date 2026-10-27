import type { BackendDescriptor } from "@agent-console/contracts";

/** 서버가 선택지에서 감추라고 표시한 백엔드인가. 판정은 디스크립터 `ui_hints.hidden`만 본다(백엔드 id는 모른다). */
export function isHiddenBackend(descriptor: Pick<BackendDescriptor, "ui_hints">): boolean {
  return descriptor.ui_hints?.hidden === true;
}

/** 선택지·목록에 보일 백엔드만 남긴다. 이미 지정된 값의 이름 표시에는 쓰지 않는다. */
export function visibleBackends<T extends Pick<BackendDescriptor, "ui_hints">>(descriptors: readonly T[]): T[] {
  return descriptors.filter((d) => !isHiddenBackend(d));
}
