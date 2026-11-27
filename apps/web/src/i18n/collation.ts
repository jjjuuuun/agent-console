import { useMemo } from "react";
import { useT } from "@agent-console/i18n";

/** 현재 화면 언어 코드(BCP 47). 언어를 바꾸면 이 값을 쓰는 화면이 다시 그려진다. */
export function useLanguageCode(): string {
  return useT("boot").language;
}

/**
 * 현재 화면 언어로 글자를 비교하는 `Intl.Collator`(정렬 기준은 언어마다 다르다). 숫자 자연 정렬 등은 `options`로.
 * @param options `Intl.CollatorOptions`(참조가 매번 달라도 내용이 같으면 다시 만들지 않는다)
 */
export function useCollator(options: Intl.CollatorOptions = {}): Intl.Collator {
  const language = useLanguageCode();
  const key = JSON.stringify(options);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- options는 key로 비교한다
  return useMemo(() => new Intl.Collator(language, options), [language, key]);
}
