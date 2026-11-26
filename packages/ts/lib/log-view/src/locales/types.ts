import type { LogViewMessages } from "../messages";
import type { BuiltinWidgetTexts } from "../widgets/builtins";

/** 로그 표시 패키지 문구 묶음 한 언어분. */
export interface LogViewLocale {
  /** 컴포넌트의 `messages` prop */
  messages: LogViewMessages;
  /** 내장 위젯 제목·설명. `createBuiltinWidgets`에 넘긴다 */
  builtinWidgets: BuiltinWidgetTexts;
}
