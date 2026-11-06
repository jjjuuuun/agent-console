import { useId, useState } from "react";
import { Banner, Button } from "@agent-console/ui";
import { folderHomeMessages as m } from "./folderHomeMessages";
import { MAX_VISIBLE_BANNERS, type BannerAction, type BannerSpec } from "./projectHomeLib";

export interface ProjectProblemBannerProps {
  banners: readonly BannerSpec[];
  /** 버튼 동작. 없는 동작의 버튼은 그리지 않는다. */
  onAction: (action: BannerAction, banner: BannerSpec) => void;
  /** 동작이 진행 중인 배너 id(버튼 잠금) */
  busy?: string | null | undefined;
  /** 마지막 [다시 확인] 결과 줄(아직 해결 안 됨 등) */
  note?: string | null | undefined;
}

const LABELS: Readonly<Record<BannerAction, string>> = {
  recheck: m.problem.recheck,
  repath: m.problem.repath,
  setFolder: m.problem.setFolder,
  unregister: m.problem.unregister,
  copyManifestPath: m.problem.manifestCopyPath,
  recreateManifest: m.problem.manifestRecreate,
  copyRecordsPath: m.problem.recordsCopyPath,
  copyBackupPath: m.problem.recordsCopyBackup,
  appendGitignore: m.problem.gitignoreAppend,
  reregister: m.problem.reregister,
};

/**
 * 프로젝트 문제 배너 묶음(표현 전용, screen-projects §6.1). 한 번에 3개까지 펼치고 나머지는 "외 n건 [모두 보기]".
 * `role="alert"`를 쓰지 않는다(화면 진입 시 읽히는 정적 문서 흐름): 영역 `aria-label`=제목.
 */
export function ProjectProblemBanner({ banners, onAction, busy, note }: ProjectProblemBannerProps) {
  const [all, setAll] = useState(false);
  const uid = useId();
  if (banners.length === 0) return null;
  const shown = all ? banners : banners.slice(0, MAX_VISIBLE_BANNERS);
  const hidden = banners.length - shown.length;
  return (
    <div className="prj-banners" data-testid="project-banners">
      {shown.map((b) => (
        <section key={b.id} role="region" aria-label={b.title} className="prj-banner" data-kind={b.kind}>
          <Banner
            tone={b.tone}
            role="presentation"
            title={b.title}
            actions={
              b.actions.length === 0 ? undefined : (
                <>
                  {b.actions.map((a, i) => (
                    <Button key={a} size="sm" variant={i === 0 && b.tone !== "info" ? "primary" : "secondary"} disabled={busy === b.id} onClick={() => onAction(a, b)}>
                      {LABELS[a]}
                    </Button>
                  ))}
                </>
              )
            }
          >
            {b.body === "" ? null : b.body}
          </Banner>
        </section>
      ))}
      {note ? <p className="prj-banner-note app-muted" id={`${uid}-note`} role="status">{note}</p> : null}
      {banners.length > MAX_VISIBLE_BANNERS ? (
        <button type="button" className="prj-link" aria-expanded={all} onClick={() => setAll((v) => !v)}>
          {all ? m.problem.showLess : `${m.problem.more(hidden)} ${m.problem.showAll}`}
        </button>
      ) : null}
    </div>
  );
}
