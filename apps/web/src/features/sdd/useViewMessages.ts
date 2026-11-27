import { useCallback, useMemo } from "react";
import { useLibMessages, useT } from "@agent-console/i18n";
import { defaultMessages } from "@agent-console/sdd-view";
import { defaultMessages as editorDefaults } from "@agent-console/markdown-doc";
import { useMaybeT } from "../../i18n/useMaybeT";

/**
 * `@agent-console/sdd-view` 문구를 앱 용어로 덮어쓴 표(그 패키지의 `defaultMessages` 키). 상태·단계·문서 이름은 없다.
 * 바탕은 패키지 문구 묶음(`sdd-view`)의 현재 언어이고, 같은 키만 앱 묶음 문구로 덮으므로 패키지 문구가 바뀌어도 이 표가 깨지지 않는다.
 */
export function useSddViewMessages(): Readonly<Record<string, string>> {
  const t = useT("sdd");
  const lib = useLibMessages("sdd-view", defaultMessages);
  return useMemo(
    () => ({
      ...lib,
      "specs.empty.title": t("list.emptyTitle"),
      "specs.empty.body": t("list.emptyBody"),
      "tasks.noSyntax.title": t("tasks.syntaxMissing.title"),
      "tasks.noSyntax.body": t("tasks.syntaxMissing.body"),
      "tasks.noSyntax.action": t("tasks.syntaxMissing.open"),
      "tasks.empty.title": t("tasks.empty.title"),
      "tasks.empty.body": t("tasks.empty.body"),
      "gate.title": t("gate.title"),
      "docs.nav": t("doc.navLabel"),
      "editor.conflict.reload": t("doc.reloadOk"),
    }),
    [lib, t],
  );
}

/**
 * 표시 데이터(`sddData.json`)가 가리키는 점 표기 문구 키(`specs.gap.*`·`specs.verification.*`) → 현재 언어 문구.
 * 빈 곳 코드·검증 결과의 이름은 서버 데이터라 묶음에는 문구만 있고 코드 분기는 없다. 키가 없으면 undefined(호출자가 원문 코드를 쓴다).
 */
export function useSpecKeyText(): (key: string | undefined) => string | undefined {
  const tm = useMaybeT("sdd");
  return useCallback((key) => (key === undefined ? undefined : tm(`specKeys.${key}`)), [tm]);
}

/** 문서 편집기(`markdown-doc`의 `DocumentEditor`)에 넘길 문구: 편집기 패키지 문구(현재 언어)에 스펙 용어 덮어쓰기를 얹는다. */
export function useSddEditorMessages(): Readonly<Record<string, string>> {
  const view = useSddViewMessages();
  const editor = useLibMessages("markdown-doc", editorDefaults);
  return useMemo(() => ({ ...editor, ...view }), [editor, view]);
}
