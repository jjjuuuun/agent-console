import { lazy, Suspense, useState, type ComponentType, type ReactNode } from "react";
import { LoadingBlock } from "../app/ErrorBlock";
import { messages } from "../app/messages";
import { ScreenBoundary } from "./ScreenBoundary";

/**
 * 화면 컴포넌트를 처음 열 때 불러오는 래퍼(번들 분할). 큰 화면(그래프·마크다운·타임라인)이 첫 화면 번들을 키우지 않게 한다.
 * @param load 동적 import 함수(예: `() => import("./Screen")`)
 * @param name 모듈에서 화면 컴포넌트를 내보낸 이름
 * @returns 같은 props를 받는 컴포넌트(불러오는 동안 로딩 표시)
 */
/** 화면 번들을 내려받지 못했다(오프라인, 배포 직후 옛 청크 등). */
export class ScreenLoadError extends Error {
  constructor(cause: unknown) {
    super("screen load failed", { cause });
    this.name = "ScreenLoadError";
  }
}

type PropsOf<C> = C extends (props: infer P) => ReactNode ? (unknown extends P ? object : P) : never;

/** `lazyScreen`이 돌려주는 컴포넌트. `preload()`로 미리 내려받을 수 있다(유휴 시간 선로딩·테스트). */
export type LazyScreenComponent<P> = ComponentType<P> & { preload: () => Promise<unknown> };

export function lazyScreen<M, K extends keyof M>(load: () => Promise<M>, name: K): LazyScreenComponent<PropsOf<M[K]>> {
  type P = PropsOf<M[K]>;
  const make = () =>
    lazy(async () => {
      try {
        return { default: (await load())[name] as unknown as ComponentType<P> };
      } catch (cause) {
        throw new ScreenLoadError(cause);
      }
    });
  // 실패한 지연 로딩은 React가 결과를 캐시하므로, 다시 시도할 때 새로 만든다
  let Screen = make();
  function LazyScreen(props: P & object) {
    const [, setAttempt] = useState(0);
    return (
      <ScreenBoundary onRetry={() => { Screen = make(); setAttempt((n) => n + 1); }} isLoadError={(e) => e instanceof ScreenLoadError}>
        <Suspense fallback={<LoadingBlock label={messages.common.loadingScreen} />}>
          <Screen {...(props as P & object)} />
        </Suspense>
      </ScreenBoundary>
    );
  }
  return Object.assign(LazyScreen, { preload: () => load() });
}
