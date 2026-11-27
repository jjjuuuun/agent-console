import type { ReactElement } from "react";
import { useT } from "@agent-console/i18n";
import { useDescribeError, type DescribeErrorFn } from "./errors";
import type { AppMessages } from "./appMessages";
import { useAppMessages } from "./appMessages";
import type { ShellMessages } from "./shellMessages";
import { useShellMessages } from "./shellMessages";

/** 알림 글을 만드는 함수가 받는 현재 화면 언어의 문구 표. */
export interface ToastTextContext {
  shell: ShellMessages;
  app: AppMessages;
}

/** 알림 글을 만드는 함수. 문구 표와, 현재 언어의 오류 코드 문구가 든 `describeError`를 받는다. */
export type ToastRender<M> = (messages: M, describe: DescribeErrorFn) => string;

/**
 * 어떤 문구 표 훅이든 묶어 알림 글 요소 만드는 컴포넌트를 돌려준다(모듈 맨 위에서 한 번 만든다).
 * 요소는 그릴 때마다 현재 화면 언어의 표로 글을 만들므로, 이미 떠 있는 알림도 언어를 바꾸면 문구만 새 언어로 바뀐다.
 * 값이 낀 문구는 `render` 안에서 만들고 값은 클로저로 넘긴다.
 * ```tsx
 * const TeamToast = createToastText(useTeamMessages);
 * toast({ text: <TeamToast render={(t) => t.editor.saved} /> });
 * ```
 */
export function createToastText<M>(useMessages: () => M): (props: { render: ToastRender<M> }) => ReactElement {
  return function ToastTextFor({ render }) {
    const messages = useMessages();
    const describe = useDescribeError();
    return <>{render(messages, describe)}</>;
  };
}

function useShellAndApp(): ToastTextContext {
  return { shell: useShellMessages(), app: useAppMessages() };
}

/**
 * 알림에 글자 대신 넘기는 요소(공용 `shell`·`app` 표). 이미 떠 있는 알림도 언어를 바꾸면 닫히지 않고 문구만 새 언어로 바뀐다.
 * `toast({ text: <ToastText render={({ shell }) => shell.pending.none} /> })`.
 */
export const ToastText = createToastText(useShellAndApp);

/**
 * `useT(namespace)` 번역 함수로 글을 만드는 알림 글 요소(모듈 맨 위에서 한 번 만든다).
 * `const SddToast = createNamespaceToastText("sdd"); toast({ text: <SddToast render={(t) => t("head.copied")} /> });`
 */
export function createNamespaceToastText(namespace: string): (props: { render: ToastRender<ReturnType<typeof useT>> }) => ReactElement {
  function useNamespaceT(): ReturnType<typeof useT> {
    return useT(namespace);
  }
  return createToastText(useNamespaceT);
}
