import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { mergeFormatters } from "./format";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { DEFAULT_SPEEDS } from "./playback";
import type { Formatters } from "./types";

export interface PlaybackBarProps {
  /** 정렬된(`sortEvents`) 재생 후보. 막대는 `seq`·`time`만 본다. */
  events: readonly { seq: number; time?: number | null }[];
  /** 보이는 마지막 인덱스(0-base). -1 = 시작 전 빈 상태. 슬라이더 값은 `index+1`. */
  index: number;
  onIndexChange: (i: number) => void;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
  speeds?: readonly number[];
  skipGaps: boolean;
  onSkipGapsChange: (v: boolean) => void;
  /** 오류 이벤트 인덱스(스크러버 틱). */
  errorIndexes?: readonly number[];
  /** 상대 시각 기준(epoch 초). 없으면 첫 이벤트 시각. */
  originTime?: number | null;
  /** `aria-valuetext`·툴팁용 이벤트 제목. */
  describe?: (i: number) => string;
  /** 끝까지 재생해 자동 정지한 상태(버튼이 ↻가 된다). */
  ended?: boolean;
  /** 끌기를 놓을 때만 위치를 확정한다(기본 true). false면 끄는 동안에도 `onIndexChange`를 부른다. */
  commitOnRelease?: boolean;
  maxTicks?: number;
  /**
   * 속도·공백 건너뛰기를 어디에 두는가. `popover`(기본) = [재생 설정 ▾] 단추 하나(속도가 1×가 아니면 단추 옆에 "2×"로 상태를 적는다),
   * `inline` = 예전처럼 막대에 select와 체크박스를 늘어놓는다.
   */
  settingsPlacement?: "popover" | "inline";
  formatters?: Partial<Formatters>;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

const clampInt = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(n)));

/**
 * 재생 막대: 재생/일시정지, 이전/다음, 스크러버(`role="slider"`), 속도, 공백 건너뛰기. 타이머는 갖지 않는다
 * (`usePlayback` 훅이 상태와 시계를 담당하고 이 컴포넌트는 값과 콜백만 받는다).
 * 슬라이더 값 `v = index + 1`(0 = 시작 전). 키보드: `←→` ±1, `Shift+←→` ±10, `PageUp/Down` ±100, `Home` 첫 이벤트, `End` 끝.
 */
export function PlaybackBar(props: PlaybackBarProps) {
  const { events, index, onIndexChange, playing, onPlayingChange, speed, onSpeedChange, speeds = DEFAULT_SPEEDS, skipGaps, onSkipGapsChange, errorIndexes = [], describe, ended, commitOnRelease = true, maxTicks = 200, settingsPlacement = "popover", ariaLabel } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const formatters = useMemo(() => mergeFormatters(props.formatters), [props.formatters]);
  const n = events.length;
  const v = clampInt(index + 1, 0, n);
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? v;
  const track = useRef<HTMLDivElement>(null);
  const id = useId();
  const origin = props.originTime ?? events[0]?.time ?? null;

  const timeOf = (val: number): string => {
    const t = events[val - 1]?.time;
    return t == null || origin == null ? m.none : formatters.relativeTime((t - origin) * 1000);
  };
  const first = events[0]?.time;
  const last = events[n - 1]?.time;
  const total = first != null && last != null ? formatters.duration(Math.max(0, (last - first) * 1000)) : m.none;
  const valueText = shown >= 1 ? fmt(m.positionText, { v: shown, n, time: timeOf(shown), title: describe?.(shown - 1) ?? "" }) : fmt(m.beforeStart, { n });

  const fromPointer = (clientX: number): number => {
    const r = track.current?.getBoundingClientRect();
    if (!r || r.width === 0) return v;
    return clampInt(((clientX - r.left) / r.width) * n, 0, n);
  };
  const commit = (val: number) => onIndexChange(clampInt(val, 0, n) - 1);
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    const val = fromPointer(e.clientX);
    setDrag(val);
    if (!commitOnRelease) commit(val);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drag === null) return;
    const val = fromPointer(e.clientX);
    setDrag(val);
    if (!commitOnRelease) commit(val);
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drag === null) return;
    commit(fromPointer(e.clientX));
    setDrag(null);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    let to: number | undefined;
    const step = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowRight") to = v + step;
    else if (e.key === "ArrowLeft") to = v - step;
    else if (e.key === "PageUp") to = v + 100;
    else if (e.key === "PageDown") to = v - 100;
    else if (e.key === "Home") to = 1;
    else if (e.key === "End") to = n;
    if (to === undefined) return;
    e.preventDefault();
    commit(to);
  };

  // 오류 틱: 같은 위치(0.1% 단위)는 하나로, 최대 maxTicks개.
  const ticks = useMemo(() => {
    const seen = new Set<number>();
    const out: number[] = [];
    for (const i of errorIndexes) {
      const pct = Math.round(((i + 1) / Math.max(n, 1)) * 1000) / 10;
      if (seen.has(pct)) continue;
      seen.add(pct);
      out.push(pct);
      if (out.length >= maxTicks) break;
    }
    return out;
  }, [errorIndexes, n, maxTicks]);

  // 재생 상태 변화만 polite로 알린다(초당 수십 건의 위치 변화는 알리지 않는다).
  const prevPlaying = useRef(playing);
  const [announce, setAnnounce] = useState("");
  useEffect(() => {
    if (playing && !prevPlaying.current) setAnnounce(m.playbackStarted);
    else if (!playing && prevPlaying.current) setAnnounce(ended || v >= n ? m.playbackEnded : m.playbackPaused);
    prevPlaying.current = playing;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);

  const atEnd = ended || (n > 0 && v >= n && !playing);
  const playLabel = playing ? m.pause : atEnd ? m.replay : m.play;
  const pct = n === 0 ? 0 : (shown / n) * 100;
  return (
    <div className="ac-lv-playbar" role="group" aria-label={ariaLabel ?? m.playback}>
      <button type="button" className="ac-lv-btn" aria-label={playLabel} title={playLabel} disabled={n === 0} onClick={() => onPlayingChange(!playing)}>
        {playing ? "⏸" : atEnd ? "↻" : "▶"}
      </button>
      <button type="button" className="ac-lv-btn" aria-label={m.prev} title={m.prev} disabled={n === 0 || v <= 0} onClick={() => commit(v - 1)}>
        ⏮
      </button>
      <button type="button" className="ac-lv-btn" aria-label={m.next} title={m.next} disabled={n === 0 || v >= n} onClick={() => commit(v + 1)}>
        ⏭
      </button>
      <div
        ref={track}
        className="ac-lv-scrub"
        role="slider"
        tabIndex={n === 0 ? -1 : 0}
        aria-label={m.scrubber}
        aria-orientation="horizontal"
        aria-valuemin={0}
        aria-valuemax={n}
        aria-valuenow={shown}
        aria-valuetext={valueText}
        aria-disabled={n === 0 || undefined}
        onKeyDown={onKey}
        onPointerDown={n === 0 ? undefined : onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => setDrag(null)}
      >
        <div className="ac-lv-scrub-track">
          <div className="ac-lv-scrub-fill" style={{ width: `${pct}%` }} />
          {ticks.map((t) => (
            <span key={t} className="ac-lv-scrub-tick" data-tone="danger" style={{ left: `${t}%` }} aria-hidden="true" />
          ))}
        </div>
        <div className="ac-lv-scrub-thumb" style={{ left: `${pct}%` }} aria-hidden="true" />
        {drag !== null ? (
          <div className="ac-lv-scrub-tip" style={{ left: `${pct}%` }} role="presentation">
            {shown >= 1 ? `${timeOf(shown)} ${describe?.(shown - 1) ?? ""}` : m.none}
          </div>
        ) : null}
      </div>
      <span className="ac-lv-num ac-lv-muted" aria-hidden="true">
        {shown >= 1 ? timeOf(shown) : m.none} / {total}
      </span>
      <span className="ac-lv-num">
        {shown} / {n}
      </span>
      {settingsPlacement === "inline" ? (
        <>
          <label className="ac-lv-inline" htmlFor={`${id}-speed`}>
            {m.speed}
            <select id={`${id}-speed`} value={speed} onChange={(e) => onSpeedChange(Number(e.target.value))}>
              {(speeds.includes(speed) ? speeds : [...speeds, speed]).map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
          <label className="ac-lv-inline">
            <input type="checkbox" checked={skipGaps} onChange={(e) => onSkipGapsChange(e.target.checked)} />
            {m.skipGaps}
          </label>
        </>
      ) : (
        <PlaybackSettings id={id} speed={speed} speeds={speeds} onSpeedChange={onSpeedChange} skipGaps={skipGaps} onSkipGapsChange={onSkipGapsChange} m={m} />
      )}
      <span role="status" aria-live="polite" className="ac-lv-sr">
        {announce}
      </span>
    </div>
  );
}

interface PlaybackSettingsProps {
  id: string;
  speed: number;
  speeds: readonly number[];
  onSpeedChange: (speed: number) => void;
  skipGaps: boolean;
  onSkipGapsChange: (v: boolean) => void;
  m: LogViewMessages;
}

/** [재생 설정 ▾]: 속도 select와 공백 건너뛰기 체크를 담은 비모달 팝오버. 바깥 클릭·`Esc`로 닫고 `Esc`면 단추로 포커스가 돌아온다. */
function PlaybackSettings({ id, speed, speeds, onSpeedChange, skipGaps, onSkipGapsChange, m }: PlaybackSettingsProps) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>("select, input")?.focus();
    const down = (e: MouseEvent) => {
      if (e.target instanceof Node && !wrap.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", down);
    return () => document.removeEventListener("mousedown", down);
  }, [open]);
  return (
    <span ref={wrap} className="ac-lv-settings">
      <button
        ref={button}
        type="button"
        className="ac-lv-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? `${id}-settings` : undefined}
        aria-label={m.playSettings}
        title={m.playSettings}
        onClick={() => setOpen(!open)}
      >
        <span className="ac-lv-wide">{m.playSettings}</span>
        <span className="ac-lv-narrow">{m.playSettingsShort}</span> ▾
      </button>
      {speed !== 1 ? <span className="ac-lv-num ac-lv-speedbadge" data-testid="speed-badge">{speed}×</span> : null}
      {open ? (
        <div
          ref={panel}
          id={`${id}-settings`}
          role="dialog"
          aria-label={m.playSettings}
          className="ac-lv-pop ac-lv-settingspop"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              setOpen(false);
              button.current?.focus();
            }
          }}
        >
          <label className="ac-lv-inline" htmlFor={`${id}-speed`}>
            {m.speed}
            <select id={`${id}-speed`} value={speed} onChange={(e) => onSpeedChange(Number(e.target.value))}>
              {(speeds.includes(speed) ? speeds : [...speeds, speed]).map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
          <label className="ac-lv-inline">
            <input type="checkbox" checked={skipGaps} onChange={(e) => onSkipGapsChange(e.target.checked)} />
            {m.skipGaps}
          </label>
        </div>
      ) : null}
    </span>
  );
}
