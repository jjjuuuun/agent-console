import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PlaybackClock } from "./types";

export interface TimedEvent {
  seq: number;
  time?: number | null;
}

/**
 * `(time, seq)` 오름차순 안정 정렬. `time`이 없는 이벤트는 `seq` 순서상 바로 앞 이벤트의 시각을 물려받아
 * 제자리(seq 위치)를 유지한다. 앞에 시각이 있는 이벤트가 없으면 맨 앞이다.
 */
export function sortEvents<T extends TimedEvent>(events: readonly T[]): T[] {
  const bySeq = [...events].sort((a, b) => a.seq - b.seq);
  let carry = Number.NEGATIVE_INFINITY;
  const keyed = bySeq.map((e) => {
    carry = e.time ?? carry;
    return { e, t: carry };
  });
  keyed.sort((a, b) => a.t - b.t || a.e.seq - b.e.seq);
  return keyed.map((k) => k.e);
}

/** `index`(0-base, 포함)까지 부분 배열. `index < 0`이면 빈 배열. */
export function visibleThrough<T>(events: readonly T[], index: number): T[] {
  return index < 0 ? [] : events.slice(0, index + 1);
}

/** URL `through=<seq>` -> 정렬된 배열의 인덱스. 없거나 못 찾으면 끝(`length-1`). */
export function indexOfSeq(sorted: readonly { seq: number }[], seq: number | null | undefined): number {
  if (seq == null) return sorted.length - 1;
  const i = sorted.findIndex((e) => e.seq === seq);
  return i < 0 ? sorted.length - 1 : i;
}

/** 인덱스 -> URL `through` 값. 끝이면 undefined(생략). */
export function seqAtIndex(sorted: readonly { seq: number }[], index: number): number | undefined {
  if (index >= sorted.length - 1 || index < 0) return undefined;
  return sorted[index]?.seq;
}

export const DEFAULT_GAP_CAP_MS = 30_000;
export const SKIP_GAP_CAP_MS = 2_000;
export const MIN_DELAY_MS = 16;

/** 다음 이벤트까지 대기 시간. `d = min(gap, cap) / speed`, 하한 16ms. */
export function playbackDelay(gapMs: number, speed: number, skipGaps: boolean, caps = { normal: DEFAULT_GAP_CAP_MS, skip: SKIP_GAP_CAP_MS }): number {
  const cap = skipGaps ? caps.skip : caps.normal;
  return Math.max(MIN_DELAY_MS, Math.min(Math.max(0, gapMs), cap) / Math.max(speed, 0.0001));
}

export interface UsePlaybackOptions {
  /** `sortEvents`로 정렬된 이벤트. */
  events: readonly TimedEvent[];
  clock: PlaybackClock;
  speeds?: readonly number[];
  /** 외부 상태로 위치를 관리할 때(URL). */
  index?: number;
  onIndexChange?: (i: number) => void;
  initialSpeed?: number;
  initialSkipGaps?: boolean;
  /** 탭이 숨겨지면 정지하는 구독(기본 document.visibilitychange). 테스트에서 끄거나 바꿔 끼운다. */
  subscribeHidden?: (onHidden: () => void) => () => void;
}

export interface PlaybackState {
  index: number;
  playing: boolean;
  speed: number;
  skipGaps: boolean;
  play(): void;
  pause(): void;
  toggle(): void;
  seek(i: number): void;
  step(delta: number): void;
  setSpeed(s: number): void;
  setSkipGaps(v: boolean): void;
  /** 끝에 닿아 자동 정지했는지(버튼이 ↻가 된다). */
  ended: boolean;
}

export const DEFAULT_SPEEDS: readonly number[] = [0.5, 1, 2, 5, 10, 30];

function defaultSubscribeHidden(onHidden: () => void): () => void {
  if (typeof document === "undefined") return () => undefined;
  const h = () => {
    if (document.hidden) onHidden();
  };
  document.addEventListener("visibilitychange", h);
  return () => document.removeEventListener("visibilitychange", h);
}

/**
 * 재생 상태기. 위치 `index`는 -1(시작 전)~N-1. 끝에서 재생하면 처음(-1)부터 시작한다.
 * 타이머는 주입된 `clock`으로만 돈다.
 */
export function usePlayback(opts: UsePlaybackOptions): PlaybackState {
  const { events, clock, speeds = DEFAULT_SPEEDS, subscribeHidden = defaultSubscribeHidden } = opts;
  const last = events.length - 1;
  const [innerIndex, setInnerIndex] = useState(last);
  const controlled = opts.index !== undefined;
  const index = Math.min(Math.max(controlled ? (opts.index as number) : innerIndex, -1), last);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeedState] = useState(opts.initialSpeed ?? speeds[Math.min(1, speeds.length - 1)] ?? 1);
  const [skipGaps, setSkipGaps] = useState(opts.initialSkipGaps ?? true);
  const [ended, setEnded] = useState(false);

  const onChange = opts.onIndexChange;
  const setIndex = useCallback(
    (i: number) => {
      const clamped = Math.min(Math.max(i, -1), last);
      if (!controlled) setInnerIndex(clamped);
      onChange?.(clamped);
    },
    [controlled, last, onChange],
  );
  const ref = useRef({ index, events, speed, skipGaps, last });
  // 타이머 콜백이 최신 값을 읽도록 렌더 뒤에 갱신한다(아래 재생 루프 effect보다 먼저 선언).
  useEffect(() => {
    ref.current = { index, events, speed, skipGaps, last };
  });

  // 재생 루프: 다음 이벤트까지의 간격만큼 기다렸다가 한 칸 전진한다.
  useEffect(() => {
    if (!playing) return;
    const { index: i, events: ev, speed: sp, skipGaps: sk, last: l } = ref.current;
    if (i >= l) {
      setPlaying(false);
      setEnded(true);
      return;
    }
    const cur = ev[i]?.time;
    const next = ev[i + 1]?.time;
    const gapMs = cur != null && next != null ? (next - cur) * 1000 : 0;
    const handle = clock.setTimeout(() => setIndex(ref.current.index + 1), playbackDelay(gapMs, sp, sk));
    return () => clock.clearTimeout(handle);
  }, [playing, index, speed, skipGaps, clock, setIndex, events.length]);

  useEffect(() => {
    if (!playing) return;
    return subscribeHidden(() => setPlaying(false));
  }, [playing, subscribeHidden]);

  const play = useCallback(() => {
    setEnded(false);
    if (ref.current.last < 0) return;
    if (ref.current.index >= ref.current.last) setIndex(-1);
    setPlaying(true);
  }, [setIndex]);
  const pause = useCallback(() => setPlaying(false), []);
  const toggle = useCallback(() => (playing ? setPlaying(false) : play()), [playing, play]);
  const seek = useCallback(
    (i: number) => {
      setPlaying(false);
      setEnded(false);
      setIndex(i);
    },
    [setIndex],
  );
  const step = useCallback((d: number) => seek(ref.current.index + d), [seek]);
  const setSpeed = useCallback((s: number) => setSpeedState(s), []);

  return useMemo(
    () => ({ index, playing, speed, skipGaps, play, pause, toggle, seek, step, setSpeed, setSkipGaps, ended }),
    [index, playing, speed, skipGaps, play, pause, toggle, seek, step, setSpeed, ended],
  );
}

/** 속도 목록에서 한 단계 느리게(-1)/빠르게(+1). 목록에 없는 값이면 가장 가까운 칸 기준. 끝에서는 멈춘다. */
export function nextSpeed(speeds: readonly number[], current: number, dir: 1 | -1): number {
  if (speeds.length === 0) return current;
  let idx = speeds.indexOf(current);
  if (idx < 0) idx = speeds.reduce((best, s, i) => (Math.abs(s - current) < Math.abs((speeds[best] as number) - current) ? i : best), 0);
  return speeds[Math.min(speeds.length - 1, Math.max(0, idx + dir))] as number;
}
