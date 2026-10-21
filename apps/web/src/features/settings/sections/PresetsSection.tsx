import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import type { ApplyPresetResult, PresetSummary } from "@agent-console/contracts";
import { contractsSchema } from "@agent-console/contracts";
import { Banner, Button, Dialog, Tag } from "@agent-console/ui";
import { useApi } from "../../../app/ApiContext";
import { describeError } from "../../../app/errors";
import { messages as m } from "../../../app/messages";
import { useProjectId } from "../../../app/projectScope";
import { enumValues } from "../../../lib/schemaTools";
import { Skeleton } from "../Skeleton";
import { usePresets } from "../settingsData";

interface PresetItem {
  kind: string;
  id: string;
  name: string;
}

function itemsOf(preset: PresetSummary): PresetItem[] {
  return (preset.items ?? []).map((raw) => ({
    kind: typeof raw["kind"] === "string" ? raw["kind"] : "",
    id: typeof raw["id"] === "string" ? raw["id"] : "",
    name: typeof raw["name"] === "string" ? raw["name"] : typeof raw["id"] === "string" ? raw["id"] : "",
  }));
}

/** 충돌 정책 어휘(계약 enum). 첫 값이 기본이 되며 계약에 없으면 서버 기본을 쓴다. */
function conflictPolicies(): string[] {
  const def = contractsSchema.$defs["ConflictPolicy"];
  return def === undefined ? [] : enumValues(def, contractsSchema);
}

export interface PresetDialogsProps {
  preset: PresetSummary | null;
  mode: "view" | "apply";
  onClose: () => void;
  /** 이미 workspace에 있는 id 목록(충돌 미리 계산·"이미 있음" 칩). 모르면 생략 */
  existingIds?: ReadonlySet<string>;
  /** 적용 결과 링크(라우트 경로). 팀 구성/에이전트 화면 위치는 호출자가 안다 */
  links?: readonly { to: string; label: string }[];
}

/**
 * 프리셋 내용 보기 / 적용 다이얼로그. 설정 화면과 채팅의 시작하기 카드가 같이 쓴다.
 * 서버 계약은 충돌 정책(`on_conflict`)만 받으므로 항목별 선택은 없다(전체 적용).
 */
export function PresetDialog({ preset, mode, onClose, existingIds, links }: PresetDialogsProps) {
  const { rest } = useApi();
  const projectId = useProjectId();
  const queryClient = useQueryClient();
  const policies = useMemo(() => conflictPolicies(), []);
  const [policy, setPolicy] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApplyPresetResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const t = m.settings.presets;
  if (preset === null) return null;
  const items = itemsOf(preset);
  const chosen = policy ?? policies[0] ?? "";
  const conflicts = existingIds === undefined ? undefined : items.filter((i) => existingIds.has(i.id)).length;

  const close = () => {
    setResult(null);
    setError(null);
    setPolicy(null);
    onClose();
  };
  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await rest.applyPreset(preset.id, { ...(chosen === "" ? {} : { on_conflict: chosen as never }), ...(projectId === null ? {} : { project: projectId }) });
      setResult(res);
      void queryClient.invalidateQueries({ queryKey: ["list"] });
    } catch (e) {
      setError(describeError(e, t.applyFailed).message);
    } finally {
      setBusy(false);
    }
  };

  const list = (
    <ul className="app-preset-items" aria-label={t.items}>
      {items.length === 0 ? <li className="app-muted">{t.itemsEmpty}</li> : null}
      {items.map((i) => (
        <li key={`${i.kind}:${i.id}`}>
          <Tag>{i.kind || "?"}</Tag> {i.name}
          {existingIds?.has(i.id) ? <span className="app-muted"> · {t.alreadyExists}</span> : null}
        </li>
      ))}
    </ul>
  );

  if (mode === "view") {
    return (
      <Dialog open title={t.viewTitle(preset.name)} onClose={close} actions={<Button onClick={close}>{m.common.close}</Button>}>
        {preset.description ? <p className="ac-text">{preset.description}</p> : null}
        {list}
      </Dialog>
    );
  }
  if (result !== null) {
    const failed = (result.items ?? []).filter((i) => i.action === "failed");
    const skipped = (result.items ?? []).filter((i) => i.action === "skipped").length;
    const created = (result.items ?? []).filter((i) => i.action !== "failed" && i.action !== "skipped").length;
    return (
      <Dialog open title={t.resultTitle} onClose={close} actions={<Button variant="primary" onClick={close}>{m.common.close}</Button>}>
        <p className="ac-text" role="status">{t.result(created, skipped, failed.length)}</p>
        {failed.length > 0 ? (
          <ul aria-label={t.failedItems}>
            {failed.map((i) => (
              <li key={`${i.kind}:${i.id}`} className="app-field-error">{i.kind} {i.id}: {i.error}</li>
            ))}
          </ul>
        ) : null}
        {(result.warnings ?? []).length > 0 ? <ul aria-label={t.warnings}>{result.warnings!.map((w) => <li key={w}>{w}</li>)}</ul> : null}
        <div className="app-inline-actions">
          {(links ?? []).map((l) => (
            <Link key={l.to} to={l.to} className="ac-btn" data-variant="secondary" data-size="md" onClick={close}>{l.label}</Link>
          ))}
        </div>
      </Dialog>
    );
  }
  return (
    <Dialog
      open
      title={t.applyTitle(preset.name)}
      onClose={close}
      actions={
        <>
          <Button onClick={close}>{m.common.cancel}</Button>
          <Button variant="primary" loading={busy} onClick={() => void apply()}>{busy ? t.applying : t.submit}</Button>
        </>
      }
    >
      {list}
      {policies.length > 0 ? (
        <fieldset className="app-fieldset">
          <legend>{t.conflictTitle}{conflicts === undefined ? "" : ` (${t.conflictCount(conflicts)})`}</legend>
          {policies.map((p) => (
            <label key={p} className="app-check">
              <input type="radio" name="on-conflict" value={p} checked={chosen === p} onChange={() => setPolicy(p)} />
              {t.conflict[p] ?? p}
            </label>
          ))}
        </fieldset>
      ) : null}
      <p className="app-muted">{t.irreversible}</p>
      {error === null ? null : <Banner tone="danger">{error}</Banner>}
    </Dialog>
  );
}

export interface PresetsSectionProps {
  existingIds?: ReadonlySet<string>;
  links?: readonly { to: string; label: string }[];
}

/** ④ 프리셋 섹션. 프리셋이 없어도 시스템은 동작하므로 안내 문구만 보인다. */
export function PresetsSection({ existingIds, links }: PresetsSectionProps) {
  const q = usePresets();
  const [active, setActive] = useState<{ preset: PresetSummary; mode: "view" | "apply" } | null>(null);
  const t = m.settings.presets;
  if (q.isLoading) return <Skeleton rows={3} />;
  if (q.error) {
    return (
      <Banner tone="danger" actions={<Button size="sm" onClick={() => void q.refetch()}>{m.common.retry}</Button>}>
        {t.loadFailed}
      </Banner>
    );
  }
  const presets = q.data ?? [];
  if (presets.length === 0) return <p className="app-muted">{t.none}</p>;
  return (
    <>
      <ul className="app-preset-list">
        {presets.map((p) => (
          <li key={p.id} className="app-preset-card">
            <div>
              <strong>{p.name}</strong> <span className="app-muted">{t.count(p.item_count ?? p.items?.length ?? 0)}</span>
              {p.description ? <p className="app-muted">{p.description}</p> : null}
              <div className="app-tags">{(p.labels ?? []).map((l) => <Tag key={l}>{l}</Tag>)}</div>
            </div>
            <div className="app-inline-actions">
              <Button size="sm" onClick={() => setActive({ preset: p, mode: "view" })}>{t.view}</Button>
              <Button size="sm" variant="primary" onClick={() => setActive({ preset: p, mode: "apply" })}>{t.apply}</Button>
            </div>
          </li>
        ))}
      </ul>
      <PresetDialog
        preset={active?.preset ?? null}
        mode={active?.mode ?? "view"}
        onClose={() => setActive(null)}
        {...(existingIds ? { existingIds } : {})}
        {...(links ? { links } : {})}
      />
    </>
  );
}

