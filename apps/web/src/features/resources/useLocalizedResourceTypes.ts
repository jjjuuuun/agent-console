import { useMemo } from "react";
import { useServerText } from "@agent-console/i18n";
import { useResourceTypes } from "../settings";

/** `useResourceTypes`와 같지만 종류 디스크립터의 제목·설명을 화면 언어로 바꾼다(서버 원문 번역). 서버 묶음에 없으면 원문 그대로다. */
export function useLocalizedResourceTypes(): ReturnType<typeof useResourceTypes> {
  const query = useResourceTypes();
  const { text } = useServerText();
  const data = query.data;
  const localized = useMemo(
    () =>
      data?.map((x) => ({
        ...x,
        title: text(x.title),
        ...(x.description ? { description: text(x.description) } : {}),
        // 아이콘 힌트가 아이콘 이름이 아니라 글자(대체 표시)면 그것도 화면 언어로 옮긴다. 아이콘 이름은 묶음에 없어 그대로다.
        ...(x.ui_hints?.icon ? { ui_hints: { ...x.ui_hints, icon: text(x.ui_hints.icon) } } : {}),
      })),
    [data, text],
  );
  return useMemo(() => ({ ...query, data: localized }) as typeof query, [query, localized]);
}
