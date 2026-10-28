import type { SectionEditProps } from "./FormSections";
import { LogsTaxonomyBlock } from "./logs/LogsTaxonomyBlock";

/**
 * 설정 "로그 분류"(`#log-taxonomy`): 범주 표시 규칙 표. 같은 설정 문서(`logs.taxonomy`)와 같은 저장 흐름(`PUT /settings` + `If-Match`, `Ctrl+S`)을
 * "로그 출처" 섹션과 함께 쓴다 — 섹션만 나뉘었다(5.7R.32). 로그 역할이 꺼져 있으면 섹션 표(`requires`)가 이 섹션을 숨긴다.
 */
export function LogTaxonomySection(props: SectionEditProps) {
  return (
    <div className="logs-settings" id="log-taxonomy-body">
      <LogsTaxonomyBlock {...props} />
    </div>
  );
}
