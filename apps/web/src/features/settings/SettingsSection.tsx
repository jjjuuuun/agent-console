import type { ReactNode } from "react";
import { Skeleton } from "./Skeleton";

export interface SettingsSectionProps {
  id: string;
  title: string;
  description?: string;
  /** 이 섹션에 필드 오류가 있다 */
  hasError?: boolean;
  /** 로딩 중이면 필드 스켈레톤 */
  loading?: boolean;
  /** 제목 옆 상태(예: "저장되지 않은 변경 2") */
  status?: string | undefined;
  children?: ReactNode;
}

/** 설정 본문의 섹션 하나: 제목 + 설명(12px muted) + 내용. 섹션 목록의 앵커 대상이다. */
export function SettingsSection({ id, title, description, hasError, loading, status, children }: SettingsSectionProps) {
  return (
    <section id={id} className="app-settings-section" aria-labelledby={`${id}-title`} data-error={hasError ? "true" : undefined}>
      <div className="app-settings-head">
        <h2 id={`${id}-title`} className="app-settings-title">
          {title}
        </h2>
        {status === undefined ? null : (
          <span className="app-settings-status" role="status">
            {status}
          </span>
        )}
      </div>
      {description === undefined ? null : <p className="app-muted app-settings-desc">{description}</p>}
      {loading ? <Skeleton rows={4} /> : children}
    </section>
  );
}
