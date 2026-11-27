import type { Translate } from "@agent-console/i18n";
import { useMessageTable } from "../../i18n";

/** 새 실행 대화상자 문구(docs/design/screen-run-start.md §5). 폴더·구성·오류 문구는 프로젝트 기능의 `targetPickerMessages`를 쓴다. */
export function createRunStartMessages(t: Translate) {
  return {
    title: t("title"),
    button: t("button"),
    submit: t("submit"),
    busy: t("busy"),
    hintShortcut: t("hintShortcut"),
    input: t("inputTitle"),
    inputNone: t("inputNone"),
    inputLoading: t("inputLoading"),
    inputLoadError: t("inputLoadError"),
    inputUnknownType: t("inputUnknownType"),
    inputRequired: t("inputRequired"),
    inputInvalidJson: t("inputInvalidJson"),
    error: t("error"),
    retry: t("retry"),
    cancel: t("cancel"),
    blockedConfig: t("blockedConfig"),
    blockedInput: t("blockedInput"),
    configLabel: t("configLabel"),
    noGraphs: t("noGraphs"),
  };
}
export type RunStartMessages = ReturnType<typeof createRunStartMessages>;

/** 현재 언어의 `runStart` 문구(렌더 때 만든다). */
export function useRunStartMessages(): RunStartMessages {
  return useMessageTable("runStart", createRunStartMessages);
}
