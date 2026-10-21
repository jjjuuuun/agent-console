import { useMemo } from "react";
import { useWorkspaceSettings } from "../../app/queries";
import { pathOptionsOf, versionBaseOf } from "./collections";
import { resolveLabelKeys } from "./versionsLogic";
import { VersionHistory, type VersionHistoryProps } from "./VersionHistory";

export interface DefinitionVersionsTabProps extends Omit<VersionHistoryProps, "base" | "pathOptions"> {
  /** 계약 모델 이름(`VERSIONED_MODELS`의 키) */
  model: string;
  /** 정의 id(설정처럼 id 없는 정의는 생략) */
  id?: string;
}

/**
 * 정의 화면의 [버전] 탭 본문: 모델 이름으로 경로와 읽는 경로 옵션을 정해 `VersionHistory`에 넘긴다.
 * 항목 이름 후보 키는 워크스페이스 설정 `ui.versions.item_label_keys`(생략 = 기본값)를 따른다.
 */
export function DefinitionVersionsTab({ model, id, ...rest }: DefinitionVersionsTabProps) {
  const base = versionBaseOf(model, id);
  const settings = useWorkspaceSettings();
  const configured = settings.data?.value.ui?.versions?.item_label_keys;
  const labelKeys = useMemo(() => resolveLabelKeys(configured), [configured]);
  const pathOptions = useMemo(() => ({ ...pathOptionsOf(model), labelKeys }), [model, labelKeys]);
  if (base === undefined) return null;
  return <VersionHistory base={base} pathOptions={pathOptions} {...rest} />;
}
