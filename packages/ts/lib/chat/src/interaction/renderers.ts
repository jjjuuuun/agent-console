import { ChoicesRenderer } from "./ChoicesRenderer";
import { PermissionRenderer } from "./PermissionRenderer";
import { ReviewRenderer } from "./ReviewRenderer";
import type { RendererComponent } from "./types";

/**
 * 기본 렌더러 표(renderer 이름 → 컴포넌트). 키는 디스크립터 `ui_hints.renderer` 문자열이다.
 * 종류 id가 아니라 렌더러 이름으로 고르므로, 새 종류가 기존 렌더러를 재사용할 수 있다.
 * `InteractionCard`의 `renderers` prop으로 더하거나 바꾼다.
 */
export const defaultRenderers: Readonly<Record<string, RendererComponent>> = {
  choices: ChoicesRenderer,
  permission: PermissionRenderer,
  review: ReviewRenderer,
};
