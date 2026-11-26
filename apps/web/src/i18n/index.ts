/** 웹 앱의 화면 언어 조립: 앱 묶음, 첫 화면 언어, 언어 고르기. 도메인 로직은 `@agent-console/i18n`에 있다. */
export { bootBundles, bundledLanguages, BOOT_NAMESPACE, loadBundled } from "./bundles";
export { browserLanguages, createAppI18n } from "./createAppI18n";
export type { CreateAppI18nOptions } from "./createAppI18n";
export { createLanguageController } from "./languageController";
export type { LanguageController, LanguageControllerDeps, LanguageState } from "./languageController";
export { FALLBACK_LANGUAGE, LANGUAGE_STORAGE_KEY, readStoredLanguage, resolveBootLanguage, writeStoredLanguage } from "./languageStorage";
export { LanguageProvider, useLanguage } from "./LanguageContext";
export type { LanguageContextValue, LanguageProviderProps } from "./LanguageContext";
export { LanguageSelect } from "./LanguageSelect";
export type { LanguageOption, LanguageSelectMessages, LanguageSelectProps } from "./LanguageSelect";
export { LanguageSetting } from "./LanguageSetting";
export { saveLanguage } from "./saveLanguage";
export { AppI18nProvider, useOptionalI18n } from "./AppI18n";
export { AppSchemaForm, useSchemaFormI18n } from "./useSchemaFormI18n";
export { AppShortcutProvider } from "./AppShortcutProvider";
