import { useMemo } from "react";
import { useLibMessages, type MessageTree } from "@agent-console/i18n";
import { createBuiltinWidgets, defaultLogViewMessages, fullTimeTitle, type Formatters, type LogViewMessages, type WidgetDescriptor } from "@agent-console/log-view";
import { ko } from "@agent-console/log-view/locales/ko";
import { useFormat } from "../../i18n";

/** 패키지 기본값(`ko`)과 같은 모양의 묶음 틀. 현재 언어의 묶음이 이 위에 덮인다. */
const DEFAULTS = { messages: defaultLogViewMessages, builtinWidgets: ko.builtinWidgets } as unknown as MessageTree;

/** 현재 언어의 `@agent-console/log-view` 묶음(컴포넌트 `messages` prop과 내장 위젯 문구). */
function useLogViewLocale(): { messages: LogViewMessages; builtinWidgets: typeof ko.builtinWidgets } {
  return useLibMessages("log-view", DEFAULTS) as unknown as { messages: LogViewMessages; builtinWidgets: typeof ko.builtinWidgets };
}

/** `@agent-console/log-view` 컴포넌트에 넘길 현재 언어의 `messages`. */
export function useLogViewMessages(): LogViewMessages {
  return useLogViewLocale().messages;
}

/** 현재 언어의 내장 위젯 서술자(제목·설명이 현재 언어). */
export function useBuiltinWidgets(): WidgetDescriptor[] {
  const { builtinWidgets } = useLogViewLocale();
  return useMemo(() => createBuiltinWidgets(builtinWidgets), [builtinWidgets]);
}

/**
 * 현재 화면 언어의 `formatters`(소요 시간·숫자·토큰·툴팁 시각). 시계 글자(`+1:23.456`, `HH:mm:ss.SSS`)는 언어와 무관해 라이브러리 기본을 쓴다.
 * 로그 컴포넌트의 `formatters` prop에 넘긴다.
 */
export function useLogViewFormatters(): Partial<Formatters> {
  const fmt = useFormat();
  return useMemo<Partial<Formatters>>(
    () => ({
      duration: (ms) => fmt.duration(ms),
      number: (n) => fmt.number(n),
      tokens: (n) => fmt.compact(n),
      fullTime: (epochSeconds) => fullTimeTitle(epochSeconds, fmt.language),
    }),
    [fmt],
  );
}
