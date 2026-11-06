/**
 * 스펙(SDD) 기능의 공개 API(다른 기능 폴더·앱 조립 층이 쓰는 것만, 가벼운 것만). 화면 컴포넌트(`SpecListScreen`·`SpecDetailScreen`·`TemplatesScreen`)는
 * 무거운 패키지(편집기·그래프)를 끌어오므로 여기서 다시 내보내지 않고 `shell/routes.tsx`가 지연 로딩으로 조립한다.
 * 문서 종류·문서 상태·작업 상태·단계·프로필 이름은 이 폴더에 없다(서버 데이터).
 */
export { SDD_ROLE, SDD_TEMPLATES_ROLE, SDD_SETTINGS_SECTION, SDD_PARAMS, gapDisplay, verificationDisplay } from "./sddConfig";
export type { ToneDisplay } from "./sddConfig";
export { sddMessages } from "./messages";
export { specsPath, specPath, specTemplatesPath } from "./sddPaths";
export { sddKeys, useSddSpace, useSddInfo, useSpecList, useSpecView, useSpecTasks, useSddLive, useInvalidateSdd } from "./useSddApi";
export { useSddContext, type SddContext } from "./useSddContext";
export { classifySddError, type SddFailure } from "./sddErrors";
export type { SddTabProps, SddTabPanels } from "./sddTabs";
// 다른 정의 종류(위키 규칙 등)가 같은 규칙 폼·위젯을 재사용한다(7R.20). 폼은 무거우므로 지연 로딩되는 화면에서만 가져다 쓴다.
export { RuleSectionsForm, type RuleSectionsFormProps } from "./RuleSectionsForm";
export { SDD_WIDGET_FIELDS } from "./widgets/fields";
export { ShapedField, IssueLines, pointerOf, rootOf, type ItemRenderArgs } from "./widgets/ShapedField";
export { SddWidgetEnvProvider, useSddWidgetEnv, type SddWidgetEnv } from "./widgets/SddWidgetEnv";
export { widgetUiSchema, widgetNameOf } from "./widgets/widgetUi";
