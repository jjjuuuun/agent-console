import type { ReactNode } from "react";
import { Link } from "react-router";
import { Button, Dialog, Icon } from "@agent-console/ui";
import type { BackendDescriptor } from "@agent-console/contracts";
import { useAppMessages } from "../../app/appMessages";
import { BackendReadinessSection } from "../backendReadiness";
import { useBackendConnectMessages } from "./messages";
import "./backendConnect.css";

export interface BackendConnectDialogProps {
  open: boolean;
  onClose: () => void;
  /** 카드를 그릴 백엔드 목록(서버 순서) */
  backends: readonly BackendDescriptor[];
  /** 공통 설정의 기본 백엔드 id: 맨 위로 올리고 [기본] 칩을 단다 */
  defaultBackendId?: string | undefined;
  /** 이 백엔드를 맨 위로 올린다(기본 칩은 그대로 기본 백엔드에만) */
  focusBackend?: string | undefined;
  /** 백엔드 상태를 첫 조회 중인가(카드 대신 불러오는 중 줄) */
  loading?: boolean;
  /** 백엔드 상태 기능이 꺼졌는가(카드 대신 안내 한 줄) */
  off?: boolean;
  /** 설정 화면의 준비 상태 칸 주소(`경로#섹션/anchor`). 없으면 링크를 그리지 않는다 */
  settingsHref?: string | undefined;
  /** 카드 맨 아래 자리(모델 줄). 없으면 카드는 그대로 */
  footer?: ((backend: BackendDescriptor) => ReactNode) | undefined;
}

/**
 * "백엔드 연결" 모달: 설정의 준비 상태 카드를 그대로 쓰므로 로그인·연결 테스트·다시 점검이 화면 이동 없이 끝난다.
 * 표현은 props, 데이터 조회는 안쪽 `BackendReadinessSection`(같은 질의 캐시). 초점·Esc·복귀는 `Dialog`가 맡는다.
 */
export function BackendConnectDialog({ open, onClose, backends, defaultBackendId, focusBackend, loading = false, off = false, settingsHref, footer }: BackendConnectDialogProps) {
  const m = useBackendConnectMessages();
  const app = useAppMessages();
  return (
    <Dialog
      open={open}
      title={m.dialog.title}
      size="lg"
      onClose={onClose}
      actions={
        <div className="app-bc-dialog-actions">
          {settingsHref === undefined || off ? <span /> : (
            <Link to={settingsHref} className="ac-btn app-bc-link" data-variant="secondary" data-size="md" onClick={onClose}>
              <span className="ac-btn-label ac-ellipsis">{m.moreInSettings}</span>
              <Icon name="chevron-right" size={14} />
            </Link>
          )}
          <Button onClick={onClose}>{app.common.close}</Button>
        </div>
      }
    >
      <div className="app-bc-dialog-body">
        {off ? (
          <p className="app-muted" role="status">{m.dialog.off}</p>
        ) : (
          <>
            <p className="app-bc-dialog-lead app-muted">{m.dialog.lead}</p>
            {loading ? (
              <div role="status" aria-busy="true" aria-label={m.dialog.loading}>
                <div className="app-skeleton-row app-bc-skeleton" />
                <span className="ac-sr-only">{m.dialog.loading}</span>
              </div>
            ) : (
              <BackendReadinessSection
                backends={backends}
                heading="hidden"
                defaultBackendId={focusBackend ?? defaultBackendId}
                titleExtra={(b) => (b.id === defaultBackendId ? <span className="app-bc-default" title={m.defaultTip}>{m.default}</span> : null)}
                {...(footer === undefined ? {} : { footer })}
              />
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
