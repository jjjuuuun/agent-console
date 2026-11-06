/**
 * 새 위키 대화상자(screen-wiki §4.1). 위키는 현재 프로젝트 폴더에만 만든다(폴더 줄은 읽기 전용).
 * 규칙은 이 공간의 위키 규칙에서 고르고(아무것도 미리 고르지 않는다) 고른 순서가 합치는 순서다. 이름·규칙 id·경로는 전부 사용자 데이터다.
 * 데이터와 콜백은 props이고 API는 부르지 않는다(제출은 `onSubmit`이 하고 실패를 던지면 이 대화상자가 문구를 보인다).
 */
import { useId, useMemo, useRef, useState } from "react";
import { Button, Dialog, Disclosure } from "@agent-console/ui";
import { RuleListEditor, type RuleSummary } from "@agent-console/wiki-view";
import type { WikiCreateRequest, WikiRuleRef, WikiRulesListItem } from "@agent-console/contracts/wiki";
import { isImeKeyEvent } from "../../lib/ime";
import { describeError } from "../../app/errors";
import { WIKI_LIMITS } from "./wikiConfig";
import { wikiMessages as m } from "./messages";

export interface NewWikiDialogProps {
  open: boolean;
  onClose: () => void;
  /** 폴더 줄(읽기 전용). 프로젝트 모듈이 없는 조립이면 생략 */
  folder?: { name: string; path?: string } | undefined;
  /** 페이지 저장 위치 줄에 쓰는 서버 값. 없으면 줄을 그리지 않는다 */
  pagesRoot?: string | undefined;
  /** 이 공간의 위키 규칙(로딩 중이면 undefined) */
  rules: readonly WikiRulesListItem[] | undefined;
  rulesFailed?: boolean;
  /**
   * [공용에서 가져오기…]. 가져온 규칙 id를 알려 주면 목록에 체크된 채 더해진다. 규칙 화면이 없는 조립이면 생략(버튼 없음).
   * 가져올 규칙이 없으면 `importDisabledReason`을 준다.
   */
  onImportRules?: (added: (ruleId: string) => void) => void;
  importDisabledReason?: string | undefined;
  /** [폴더 압축 파일에서 가져오기…]. 가져오기 기능이 없는 조립이면 생략 */
  onImportZip?: (() => void) | undefined;
  /** 규칙 화면 열기(규칙 행의 [열기]). 화면이 없으면 생략 */
  onOpenRule?: ((id: string) => void) | undefined;
  /** 읽기 전용·폴더 문제 이유. 있으면 제출이 막힌다 */
  blockedReason?: string | undefined;
  onSubmit: (body: WikiCreateRequest) => Promise<void>;
}

export function NewWikiDialog({ open, onClose, folder, pagesRoot, rules, rulesFailed = false, onImportRules, importDisabledReason, onImportZip, onOpenRule, blockedReason, onSubmit }: NewWikiDialogProps) {
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [id, setId] = useState("");
  const [description, setDescription] = useState("");
  const [home, setHome] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const nameId = useId();
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const byId = useMemo(() => new Map((rules ?? []).map((r) => [r.id, r])), [rules]);
  const summaryOf = (r: WikiRulesListItem): RuleSummary => ({ id: r.id, name: r.name ?? r.id, ...(r.counts === undefined ? {} : { counts: r.counts }), ...(r.has_instructions === undefined ? {} : { has_instructions: r.has_instructions }) });
  const value: WikiRuleRef[] = chosen.map((rid) => ({ id: rid, name: byId.get(rid)?.name ?? rid, missing: !byId.has(rid) }));
  const summaries = Object.fromEntries((rules ?? []).map((r) => [r.id, summaryOf(r)]));
  const available = (rules ?? []).filter((r) => !chosen.includes(r.id)).map(summaryOf);

  const submit = async () => {
    if (busy) return;
    if (blocked) return;
    if (name.trim() === "") {
      setNameError(m.newWiki.nameRequired);
      nameRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setNameError(null);
    try {
      await onSubmit({
        name: name.trim(),
        ...(id.trim() === "" ? {} : { id: id.trim() }),
        ...(description.trim() === "" ? {} : { description: description.trim() }),
        ...(home.trim() === "" ? {} : { home: home.trim() }),
        rules: chosen,
      });
    } catch (e) {
      setError(describeError(e, m.newWiki.failed).message);
    } finally {
      setBusy(false);
    }
  };
  const location = pagesRoot === undefined || pagesRoot === "" ? null : m.newWiki.location(`${pagesRoot}/${id.trim() === "" ? m.newWiki.idAuto : id.trim()}/…`);
  return (
    <Dialog
      open={open}
      title={m.newWiki.title}
      size="lg"
      onClose={() => {
        if (!busy) onClose();
      }}
      initialFocus={nameRef}
      actions={
        <>
          {location === null ? null : <span className="app-muted wiki-dialog-foot ac-mono-wrap">{location}</span>}
          <Button onClick={onClose} disabled={busy}>{m.cancel}</Button>
          <Button variant="primary" aria-disabled={blocked || busy || undefined} title={blocked ? blockedReason : undefined} onClick={() => void submit()}>
            {busy ? m.newWiki.submitting : m.newWiki.submit}
          </Button>
        </>
      }
    >
      <div
        className="wiki-form"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !isImeKeyEvent(e.nativeEvent)) void submit();
        }}
      >
        {error === null ? null : <p className="app-field-error" role="alert" data-testid="wiki-new-error">{error}</p>}
        {folder === undefined ? null : (
          <div className="wiki-field">
            <span className="wiki-label">{m.newWiki.folder}</span>
            <span className="wiki-readonly-line ac-mono-wrap">{folder.name}{folder.path === undefined || folder.path === "" ? "" : ` · ${folder.path}`}</span>
          </div>
        )}
        <label className="wiki-field" htmlFor={nameId}>
          <span className="wiki-label">{m.newWiki.name} *</span>
          <input
            id={nameId}
            ref={nameRef}
            className="wiki-input"
            value={name}
            maxLength={WIKI_LIMITS.nameMax}
            placeholder={m.newWiki.namePlaceholder}
            aria-invalid={nameError !== null || undefined}
            onChange={(e) => setName(e.target.value)}
          />
          {nameError === null ? null : <span className="app-field-error" role="alert">{nameError}</span>}
        </label>
        <div className="wiki-field">
          <span className="wiki-label">{m.newWiki.rules}</span>
          <span className="app-muted wiki-hint">{m.newWiki.rulesHint}</span>
          {rulesFailed ? (
            <p className="app-field-error" role="alert">{m.newWiki.rulesFailed}</p>
          ) : rules !== undefined && rules.length === 0 && chosen.length === 0 ? (
            <p className="app-muted" data-testid="wiki-new-rules-none">{m.newWiki.rulesNone}</p>
          ) : null}
          <RuleListEditor
            value={value}
            summaries={summaries}
            available={available}
            readOnly={blocked}
            {...(blocked ? { readOnlyReason: blockedReason } : {})}
            onChange={(next) => setChosen(next)}
            {...(onOpenRule === undefined ? {} : { onOpen: onOpenRule })}
            {...(onImportRules === undefined ? {} : { onImport: () => onImportRules((ruleId) => setChosen((cur) => (cur.includes(ruleId) ? cur : [...cur, ruleId]))) })}
          />
          {onImportRules !== undefined && importDisabledReason !== undefined ? <span className="app-muted wiki-hint">{importDisabledReason}</span> : null}
        </div>
        <Disclosure summary={m.newWiki.advanced}>
          <div className="wiki-form">
            <label className="wiki-field">
              <span className="wiki-label">{m.newWiki.id}</span>
              <input className="wiki-input ac-mono" value={id} placeholder={m.newWiki.idAuto} onChange={(e) => setId(e.target.value)} />
            </label>
            <label className="wiki-field">
              <span className="wiki-label">{m.newWiki.description}</span>
              <input className="wiki-input" value={description} onChange={(e) => setDescription(e.target.value)} />
            </label>
            <label className="wiki-field">
              <span className="wiki-label">{m.newWiki.home}</span>
              <input className="wiki-input ac-mono" value={home} onChange={(e) => setHome(e.target.value)} />
              <span className="app-muted wiki-hint">{m.newWiki.homeHint}</span>
            </label>
          </div>
        </Disclosure>
        {onImportZip === undefined ? null : (
          <p className="app-muted">
            {m.newWiki.importAsk}{" "}
            <button type="button" className="app-link-btn" onClick={onImportZip}>{m.newWiki.importLink}</button>
          </p>
        )}
      </div>
    </Dialog>
  );
}
