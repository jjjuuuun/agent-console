import { useMemo } from "react";
import { useLibMessages, useT } from "@agent-console/i18n";
import { defaultMessages } from "@agent-console/markdown-doc";

/**
 * `@agent-console/markdown-doc`의 편집기 문구를 위키 용어로 덮은 표. 충돌 띠는 "서버 버전 불러오기 / 변경 비교 / 내 변경으로 덮어쓰기 / 내 변경 복사"
 * 네 버튼이다. 그 밖의 문구는 패키지 문구 묶음(`markdown-doc`)의 현재 언어를 쓴다.
 * `{file}`은 패키지가 채우는 자리라서 그대로 남겨 넘긴다.
 */
export function useWikiEditorMessages(): Readonly<Record<string, string>> {
  const t = useT("wiki");
  const lib = useLibMessages("markdown-doc", defaultMessages);
  return useMemo(
    () => ({
      ...lib,
      "editor.conflict.title": t("band.conflict"),
      "editor.conflict.body": t("editorLib.conflictBody"),
      "editor.conflict.reload": t("band.loadServer"),
      "editor.external.body": t("editorLib.externalBody"),
      "editor.missing.title": t("editorLib.missingTitle"),
      "editor.missing.body": t("editorLib.missingBody", { file: "{file}" }),
      "editor.readOnly.body": t("editorLib.readOnlyBody"),
      "editor.empty": t("editorLib.empty"),
    }),
    [lib, t],
  );
}
