import { useMemo, useRef, type CompositionEventHandler } from "react";

/** 키 이벤트가 IME 조합 중(또는 조합 확정 키)인지 보는 데 필요한 최소 모양. React·DOM 이벤트 모두 맞는다. */
export interface ImeKeyEventLike {
  keyCode?: number;
  isComposing?: boolean;
  nativeEvent?: { isComposing?: boolean; keyCode?: number };
}

/** 한글·일본어 등 조합 입력 중의 키인가(`isComposing` 또는 `keyCode === 229`). 상태가 필요 없는 판정. */
export function isImeKeyEvent(e: ImeKeyEventLike): boolean {
  return e.isComposing === true || e.nativeEvent?.isComposing === true || e.keyCode === 229 || e.nativeEvent?.keyCode === 229;
}

export interface ImeGuard {
  /** 입력 요소에 펼친다(`<input {...guard.handlers} />`). 조합 시작·끝을 기록한다 */
  handlers: { onCompositionStart: CompositionEventHandler; onCompositionEnd: CompositionEventHandler };
  /**
   * 이 키 이벤트를 Enter 등의 동작으로 처리하면 안 되는가: 조합 중, 키코드 229, 조합이 막 확정된 직후(한 틱).
   * 브라우저에 따라 조합 확정 Enter가 `compositionend` 뒤에 `isComposing=false`로 오기 때문이다.
   */
  isIme: (e: ImeKeyEventLike) => boolean;
}

/**
 * IME Enter 가드. `isComposing`만 보면 확정 Enter가 새어 나가는 브라우저가 있어,
 * 조합 중 + keyCode 229 + 확정 직후 한 틱까지 막는다. 입력 요소마다 하나씩 쓴다.
 */
export function useImeGuard(): ImeGuard {
  const composing = useRef(false);
  const justEnded = useRef(false);
  return useMemo<ImeGuard>(
    () => ({
      handlers: {
        onCompositionStart: () => {
          composing.current = true;
        },
        onCompositionEnd: () => {
          composing.current = false;
          justEnded.current = true;
          setTimeout(() => {
            justEnded.current = false;
          }, 0);
        },
      },
      isIme: (e) => composing.current || justEnded.current || isImeKeyEvent(e),
    }),
    [],
  );
}
