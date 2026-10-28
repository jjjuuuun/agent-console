import { Banner, Button, IconButton } from "@agent-console/ui";
import { archMessages as t } from "../messages";
import type { ArchPopout } from "./useArchPopout";

const svgProps = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true, focusable: false } as const;

/** 새 창으로 보내기 아이콘(네모에서 나가는 화살표). */
export function PopoutIcon() {
  return (
    <svg {...svgProps}>
      <path d="M9 2.5h4.5V7M13.5 2.5 7.5 8.5M12 9.5v3a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3" />
    </svg>
  );
}

/** 구조도 도구줄에 놓는 [새 창으로 분리] 아이콘 단추. 분리를 쓸 수 없으면 그리지 않는다. */
export function PopoutButton({ popout }: { popout: ArchPopout }) {
  if (!popout.supported) return null;
  return <IconButton size="sm" label={t.popout.open} aria-haspopup="dialog" icon={<PopoutIcon />} onClick={popout.open} data-testid="arch-popout-open" />;
}

/** 팝업이 막혔을 때의 안내. */
export function PopoutNotice({ popout }: { popout: ArchPopout }) {
  if (!popout.blocked) return null;
  return (
    <Banner tone="warning" className="arch-banner" role="alert">
      {t.popout.blocked}
    </Banner>
  );
}

/** 분리 중(또는 분리해서 보기로 기억됨)일 때 구조도 자리에 접어서 보이는 안내와 [다시 합치기]. */
export function PopoutPlaceholder({ popout }: { popout: ArchPopout }) {
  const pending = popout.mode === "pending";
  return (
    <section className="arch-popout-fold" aria-label={t.region} data-popout={popout.mode} data-testid="arch-popout-fold">
      <div className="arch-popout-fold-text">
        <strong>{pending ? t.popout.pendingTitle : t.popout.detachedTitle}</strong>
        <span className="app-muted">{pending ? t.popout.pendingBody : t.popout.detachedBody}</span>
      </div>
      <div className="arch-popout-fold-actions">
        {pending ? (
          <Button size="sm" variant="primary" onClick={popout.open}>{t.popout.open}</Button>
        ) : (
          <Button size="sm" onClick={popout.open}>{t.popout.focus}</Button>
        )}
        <Button size="sm" onClick={popout.redock} data-testid="arch-popout-redock">{pending ? t.popout.dock : t.popout.redock}</Button>
      </div>
      <PopoutNotice popout={popout} />
    </section>
  );
}
