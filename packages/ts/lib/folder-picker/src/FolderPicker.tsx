import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent, type ReactElement, type Ref } from "react";

import { browseStartPath, deriveCheckState, type FolderCheckState } from "./checkState";
import { FolderBrowser } from "./FolderBrowser";
import { FolderCheckResult } from "./FolderCheckResult";
import { FolderPathInput } from "./FolderPathInput";
import { FolderPickStatusLine, type FolderSelectPhase } from "./FolderPickStatus";
import { Icon } from "./icons";
import { createTranslate, type MessageOverrides } from "./messages";
import { SelectedFolder } from "./SelectedFolder";
import type { FolderCapabilitiesData, FolderCheckFn, FolderCheckOutcome, FolderCreateFn, FolderListFn, FolderPickFn, FolderPickOutcome, FolderRootData } from "./types";
import { useAfter } from "./useAfter";
import { useFolderCheck } from "./useFolderCheck";
import { withDir } from "./withDir";

export interface FolderPickerProps {
  /** 요소 id 접두. */
  id: string;
  /** 선택한 폴더 경로(비면 아직 선택 전). */
  value: string;
  onValueChange: (value: string) => void;
  check: FolderCheckFn;
  list: FolderListFn;
  createFolder?: FolderCreateFn;
  roots: readonly FolderRootData[];
  /**
   * 서버가 제공하는 폴더 고르기 방법. `native_dialog: true`면 [폴더 선택…]이 OS 선택 창(`onPickNative`)을 열고,
   * `false`면 앱 안 찾아보기 패널을 연다. `browse: false`면 버튼을 막고 직접 입력을 연다.
   * 아직 조회 중이거나 실패했으면 null·생략(선택 창을 먼저 시도하고, `unavailable`이면 찾아보기로 넘어간다).
   */
  capabilities?: FolderCapabilitiesData | null;
  /** OS 선택 창 콜백(서버 API는 모른다). 없으면 [폴더 선택…]이 찾아보기 패널을 연다. */
  onPickNative?: FolderPickFn;
  /** 앱이 프로젝트 구성을 담는 폴더 이름. 주면 "이 폴더에 {dir} 폴더를 만듭니다" 줄과 `{dir}` 문구를 쓴다(고정폭). */
  configDir?: string;
  /** 문구 덮어쓰기(키는 `defaultMessages`). */
  messages?: MessageOverrides;
  /**
   * 경로 다시 지정 모드: 자기 자신을 겹침 검사에서 빼려고 확인 요청에 실을 프로젝트 id.
   * 등록(add) 모드에서는 생략한다.
   */
  excludeProjectId?: string;
  /** 경로 다시 지정 모드의 이전 경로: 확인된 경로와 같으면 `same_path`, 입력이 빈 채 열면 이 경로를 기준으로 시작 위치를 정한다. */
  currentFolder?: string | null;
  disabled?: boolean;
  /** 확인 상태가 바뀔 때마다. 제출 버튼 활성 여부는 `state.submittable`과 `selectPhase !== "waiting"`로 정한다. */
  onStateChange?: (state: FolderCheckState) => void;
  /** 선택 흐름 단계가 바뀔 때마다(`waiting`이면 앱이 제출 버튼을 막는다). */
  onSelectPhaseChange?: (phase: FolderSelectPhase) => void;
  /** 직접 입력 칸에서 Enter를 눌렀고 이미 제출할 수 있는 상태일 때. */
  onSubmit?: () => void;
  /** [열기]·[그 프로젝트 열기]. 없으면 버튼을 그리지 않는다. */
  onOpenProject?: (projectId: string) => void;
  /** 폴더를 골랐을 때(OS 선택 창 또는 찾아보기 [이 폴더 선택]) 확인 상태와 함께. 앱이 포커스를 제출 버튼으로 옮길 때 쓴다. */
  onPicked?: (path: string, state: FolderCheckState) => void;
  /** [폴더 선택…] 버튼 ref(첫 포커스 지정용). */
  pickRef?: Ref<HTMLButtonElement | null>;
  /** 직접 입력 칸 ref(칸이 펼쳐져 있을 때만 연결된다). */
  inputRef?: Ref<HTMLInputElement>;
  /** 마운트 때 [폴더 선택…]에 포커스를 준다(대화상자 첫 포커스). */
  autoFocus?: boolean;
  /** "경로를 직접 입력"을 처음부터 펼친다. 기본 접힘. */
  defaultManualOpen?: boolean;
  hideLabel?: boolean;
  /** 직접 입력 디바운스(ms). 선택한 경로는 늘 즉시 확인한다. 기본 300. */
  debounceMs?: number;
  /** 대기가 이 시간(ms)을 넘으면 [앱 안에서 찾아보기]를 보인다. 기본 30000. */
  waitingEscapeMs?: number;
  /** "선택을 취소했습니다" 알림을 보이는 시간(ms). 기본 3000. */
  cancelledNoticeMs?: number;
  /** 경로 복사 구현(기본 `navigator.clipboard`). */
  copy?: (text: string) => Promise<void> | void;
}

/**
 * 폴더 고르기 컨테이너(선택 우선 배치): 선택한 폴더 상자 + [폴더 선택…] + 선택 흐름 상태 + 직접 입력(접힘) + 확인 결과 + 찾아보기 패널.
 * 서버 호출은 `check`·`list`·`createFolder`·`onPickNative`로 주입받는다. 이름·id·제출은 앱이 맡는다.
 */
export function FolderPicker(props: FolderPickerProps): ReactElement {
  const {
    id, value, onValueChange, check, list, createFolder, roots, capabilities, onPickNative, configDir, messages, excludeProjectId, currentFolder, disabled,
    onStateChange, onSelectPhaseChange, onSubmit, onOpenProject, onPicked, pickRef, inputRef, autoFocus, defaultManualOpen = false, hideLabel, debounceMs,
    waitingEscapeMs = 30000, cancelledNoticeMs = 3000, copy,
  } = props;
  const t = useMemo(() => createTranslate(messages), [messages]);
  const fc = useFolderCheck({ check, excludeProjectId, currentFolder, debounceMs });
  const { state, request, flush, checkNow, adopt, recheck, createHere, creating } = fc;
  const [open, setOpen] = useState<{ start: string | null; note: string | null; seq: number } | null>(null);
  const [opening, setOpening] = useState(false);
  const [phase, setPhaseState] = useState<FolderSelectPhase>("idle");
  const [reason, setReason] = useState<string | null>(null);
  const [nativeOff, setNativeOff] = useState(false);
  const [manualOpen, setManualOpen] = useState(defaultManualOpen);
  const pickBtn = useRef<HTMLButtonElement>(null);
  const altBtn = useRef<HTMLButtonElement>(null);
  const opener = useRef<"pick" | "alt">("pick");
  const lastRequested = useRef("");
  const seq = useRef(0);
  const pickSeq = useRef(0);
  const pickCtl = useRef<AbortController | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useImperativeHandle(pickRef, () => pickBtn.current as HTMLButtonElement, []);
  useEffect(() => {
    if (autoFocus) pickBtn.current?.focus();
  }, [autoFocus]);

  const setPhase = useCallback((next: FolderSelectPhase) => setPhaseState(next), []);
  useEffect(() => {
    onSelectPhaseChange?.(phase);
  }, [phase, onSelectPhaseChange]);

  const clearNotice = () => {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = null;
  };
  useEffect(
    () => () => {
      clearNotice();
      pickSeq.current += 1;
      pickCtl.current?.abort();
    },
    [],
  );

  // 앱이 값을 바꾸면(미리 채우기 등) 즉시 확인한다. 우리가 낸 변경은 lastRequested와 같아 건너뛴다.
  useEffect(() => {
    if (value !== lastRequested.current) {
      lastRequested.current = value;
      request(value, { immediate: true });
    }
  }, [value, request]);

  useEffect(() => {
    onStateChange?.(state);
  }, [state, onStateChange]);

  // 직접 입력: 디바운스. 선택·붙여넣기는 즉시.
  const change = useCallback(
    (next: string, source: "type" | "paste") => {
      lastRequested.current = next;
      onValueChange(next);
      request(next, { immediate: source === "paste" });
      setOpen((o) => (o ? { ...o, note: null } : o));
      setPhaseState((p) => (p === "waiting" ? p : "idle"));
    },
    [onValueChange, request],
  );

  /** 찾아보기·선택 창의 시작 위치(K33-13): 선택한 경로 → 가장 가까운 존재하는 상위 → (다시 지정이면 이전 경로 기준) → roots. */
  const resolveStart = async (): Promise<{ start: string | null; note: string | null }> => {
    let st = await flush();
    let start = browseStartPath(st);
    if (start === null && value.trim() === "" && currentFolder) {
      try {
        const out = await check({ path: currentFolder, ...(excludeProjectId ? { excludeProjectId } : {}) }, new AbortController().signal);
        st = deriveCheckState(currentFolder, out, { currentFolder });
        start = browseStartPath(st);
      } catch {
        start = null;
      }
    }
    const usedNearest = st.check !== null && start !== null && st.check.path !== start;
    return { start, note: usedNearest ? start : null };
  };

  const openBrowse = async (by: "pick" | "alt") => {
    setOpening(true);
    try {
      const { start, note } = await resolveStart();
      seq.current += 1;
      opener.current = by;
      setOpen({ start, note, seq: seq.current });
    } finally {
      setOpening(false);
    }
  };
  const closeBrowse = () => {
    setOpen(null);
    (opener.current === "alt" ? altBtn.current ?? pickBtn.current : pickBtn.current)?.focus();
  };

  const finishCancelled = () => {
    clearNotice();
    setPhase("cancelled");
    noticeTimer.current = setTimeout(() => {
      noticeTimer.current = null;
      setPhaseState((p) => (p === "cancelled" ? "idle" : p));
    }, cancelledNoticeMs);
    pickBtn.current?.focus();
  };

  /** 대기 중인 OS 선택 창 요청을 끊는다(서버가 창을 닫는다). */
  const cancelPick = () => {
    pickSeq.current += 1;
    pickCtl.current?.abort();
    pickCtl.current = null;
    finishCancelled();
  };

  const startNative = async () => {
    if (!onPickNative) return;
    const my = ++pickSeq.current;
    clearNotice();
    setReason(null);
    setOpen(null);
    setPhase("waiting");
    const ctl = new AbortController();
    pickCtl.current = ctl;
    let initial: string | undefined;
    try {
      initial = (await resolveStart()).start ?? undefined;
    } catch {
      initial = undefined;
    }
    if (my !== pickSeq.current) return;
    let res: FolderPickOutcome;
    try {
      res = await onPickNative(initial, ctl.signal);
    } catch {
      if (my !== pickSeq.current) return;
      pickCtl.current = null;
      if (ctl.signal.aborted) finishCancelled();
      else {
        setPhase("failed");
        await openBrowse("pick");
      }
      return;
    }
    if (my !== pickSeq.current) return;
    pickCtl.current = null;
    switch (res.status) {
      case "picked": {
        const path = res.path?.trim() ?? "";
        if (path === "") {
          setPhase("failed");
          await openBrowse("pick");
          return;
        }
        lastRequested.current = path;
        onValueChange(path);
        const given: FolderCheckOutcome | null = res.outcome ?? (res.check ? { kind: "checked", check: res.check } : null);
        const st = given ? adopt(path, given) : await checkNow(path);
        if (my !== pickSeq.current) return;
        setPhase("picked");
        pickBtn.current?.focus();
        onPicked?.(path, st);
        return;
      }
      case "cancelled":
        finishCancelled();
        return;
      case "busy":
      case "timeout":
        setPhase(res.status === "busy" ? "busy" : "timeout");
        return;
      case "unavailable":
        setNativeOff(true); // 이 컴퓨터는 선택 창을 못 쓴다: 이후 같은 버튼이 곧바로 패널을 연다
        setReason(res.reason ?? null);
        setPhase("unavailable");
        await openBrowse("pick");
        return;
      default:
        setReason(res.reason ?? null);
        setPhase("failed");
        await openBrowse("pick");
    }
  };

  const waiting = phase === "waiting";
  const escapeVisible = useAfter(waiting, waitingEscapeMs);
  const browseOnly = capabilities?.browse === false;
  const nativeUsable = onPickNative !== undefined && !nativeOff && (capabilities == null || capabilities.native_dialog === true);
  const blocked = state.browseDisabled || (browseOnly && !nativeUsable);
  const blockedTip = t("folder.check.remote_disabled");

  const onPickClick = () => {
    if (blocked || waiting) return;
    if (nativeUsable) void startNative();
    else if (open) setOpen(null);
    else void openBrowse("pick");
  };
  const onUseBrowser = () => {
    if (waiting) cancelPick();
    clearNotice();
    setPhaseState((p) => (p === "busy" || p === "timeout" || p === "waiting" ? "idle" : p));
    void openBrowse("alt");
  };

  const navigate = (path: string) => {
    lastRequested.current = path;
    onValueChange(path);
    request(path, { immediate: true });
  };

  const onEnter = () => {
    if (state.group === "checking") void flush();
    else if (state.submittable) onSubmit?.();
    else if (value.trim() !== "" && state.group !== "idle") recheck();
  };

  // 대기 중 Esc는 대화상자가 아니라 선택을 취소한다. 그다음 찾아보기 패널 접기. 대화상자 닫기는 앱 몫이다.
  const onRootKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Escape") return;
    if (waiting) {
      e.stopPropagation();
      cancelPick();
    } else if (open) {
      e.stopPropagation();
      closeBrowse();
    }
  };

  const hasSelection = value.trim() !== "";
  const browseId = `${id}-browser`;
  const manualId = `${id}-manual`;
  const manualVisible = manualOpen || blocked || browseOnly;
  const nativeMode = nativeUsable;
  const showAlt = nativeMode && hasSelection && !waiting && phase !== "busy" && phase !== "timeout"; // busy·timeout 줄에 같은 버튼이 있다
  const hideCreatesDir = state.id === "manifest_found" || state.id === "manifest_invalid" || state.id === "ok_readonly";

  const pickLabel = waiting ? t("folder.pick.waiting") : hasSelection ? t("folder.pick.again") : t("folder.pick.action");

  return (
    <div className="ac-fp-root ac-fp-picker" onKeyDown={onRootKeyDown} data-select-phase={phase}>
      <SelectedFolder id={id} t={t} path={value} hideLabel={hideLabel} copy={copy} />
      <div className="ac-fp-pickrow">
        <button
          ref={pickBtn}
          type="button"
          className="ac-fp-btn ac-fp-pickbtn"
          data-size="lg"
          data-variant={hasSelection ? undefined : "primary"}
          aria-disabled={blocked || waiting ? "true" : undefined}
          aria-expanded={nativeMode ? undefined : open !== null}
          aria-controls={nativeMode ? undefined : browseId}
          aria-busy={waiting ? "true" : undefined}
          disabled={disabled || (opening && !waiting)}
          title={blocked ? blockedTip : undefined}
          onClick={onPickClick}
        >
          {waiting ? <span className="ac-fp-spinner" aria-hidden="true" /> : null}
          {pickLabel}
        </button>
        {waiting ? (
          <button type="button" className="ac-fp-btn" onClick={cancelPick}>{t("folder.pick.cancel")}</button>
        ) : null}
        {showAlt ? (
          <button
            ref={altBtn}
            type="button"
            className="ac-fp-btn"
            data-variant="text"
            aria-expanded={open !== null}
            aria-controls={browseId}
            disabled={disabled || opening}
            onClick={() => (open ? closeBrowse() : void openBrowse("alt"))}
          >
            {open ? t("folder.browse.close") : t("folder.pick.use_browser")}
          </button>
        ) : null}
      </div>
      <FolderPickStatusLine
        id={`${id}-pick-status`}
        t={t}
        phase={phase}
        escapeVisible={escapeVisible}
        reason={reason}
        disabled={disabled}
        onRetry={() => void startNative()}
        onUseBrowser={onUseBrowser}
      />
      {blocked ? <p className="ac-fp-help">{blockedTip}</p> : null}

      <div className="ac-fp-disclosure">
        <button
          type="button"
          className="ac-fp-disclosure-btn"
          aria-expanded={manualVisible}
          aria-controls={manualId}
          onClick={() => setManualOpen((o) => !o)}
        >
          <Icon name="chevron-right" className="ac-fp-disclosure-icon" />
          {t("folder.path.manual")}
        </button>
        <div id={manualId} className="ac-fp-disclosure-body" hidden={!manualVisible}>
          {manualVisible ? (
            <FolderPathInput
              id={id}
              value={value}
              t={t}
              state={state}
              disabled={disabled || waiting}
              inputRef={inputRef}
              label={t("folder.path.input_label")}
              showResult={false}
              onValueChange={change}
              onBlur={() => void flush()}
              onEnter={onEnter}
            />
          ) : null}
        </div>
      </div>

      {configDir && !hideCreatesDir ? <p className="ac-fp-help ac-fp-creates">{withDir(t("folder.check.creates_dir"), configDir)}</p> : null}
      <FolderCheckResult
        id={`${id}-result`}
        state={state}
        t={t}
        creating={creating}
        configDir={configDir}
        onCreate={createHere}
        onRecheck={recheck}
        onOpenProject={onOpenProject}
      />
      {open && !blocked ? (
        <FolderBrowser
          key={open.seq}
          id={browseId}
          t={t}
          roots={roots}
          startPath={open.start}
          list={list}
          createFolder={createFolder}
          nearestNote={open.note}
          disabled={disabled}
          onNavigate={navigate}
          onSelect={(path) => {
            setOpen(null);
            pickBtn.current?.focus();
            setPhase("picked");
            onPicked?.(path, state);
          }}
          onClose={closeBrowse}
        />
      ) : null}
    </div>
  );
}
