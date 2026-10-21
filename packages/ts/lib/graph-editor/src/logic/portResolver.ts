import type { PortSpec } from "@agent-console/contracts";

export type ResolvePortsFn = (typeId: string, config: unknown) => Promise<PortSpec>;

/** 키 순서에 무관한 안정 직렬화(캐시 키용). */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(",")}}`;
}

export interface PortEntry {
  /** 마지막으로 성공한 포트(요청 중·실패 시에도 유지) */
  ports: PortSpec | undefined;
  loading: boolean;
  failed: boolean;
}

export interface PortResolverOptions {
  resolve: ResolvePortsFn;
  /** 디바운스(ms). 기본 300 */
  delayMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

const EMPTY: PortEntry = { ports: undefined, loading: false, failed: false };

/**
 * 동적 포트 계산기: 노드별 디바운스 + (타입+config) 캐시 + 경합 시 마지막 요청만 채택.
 * UI와 무관한 순수 로직. React에서는 useSyncExternalStore로 구독한다.
 */
export class PortResolver {
  private resolveFn: ResolvePortsFn;
  private readonly delay: number;
  private readonly setTimer: (fn: () => void, ms: number) => unknown;
  private readonly clearTimer: (h: unknown) => void;
  private readonly cache = new Map<string, PortSpec>();
  private readonly want = new Map<string, string>(); // nodeId -> 현재 원하는 키
  private readonly timers = new Map<string, unknown>();
  private entries = new Map<string, PortEntry>();
  private readonly listeners = new Set<() => void>();
  private version = 0;

  constructor(opts: PortResolverOptions) {
    this.resolveFn = opts.resolve;
    this.delay = opts.delayMs ?? 300;
    this.setTimer = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
    this.clearTimer = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
  }

  setResolve(fn: ResolvePortsFn): void {
    this.resolveFn = fn;
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getVersion = (): number => this.version;

  get(nodeId: string): PortEntry {
    return this.entries.get(nodeId) ?? EMPTY;
  }

  private set(nodeId: string, entry: PortEntry): void {
    this.entries = new Map(this.entries).set(nodeId, entry);
    this.version += 1;
    for (const l of this.listeners) l();
  }

  /** 노드의 현재 (타입, config)를 알린다. 같은 키면 아무 일도 하지 않는다. */
  request(nodeId: string, typeId: string, config: unknown): void {
    const key = `${typeId}\u0000${stableStringify(config ?? {})}`;
    if (this.want.get(nodeId) === key) return;
    this.want.set(nodeId, key);
    const pending = this.timers.get(nodeId);
    if (pending !== undefined) {
      this.clearTimer(pending);
      this.timers.delete(nodeId);
    }
    const cached = this.cache.get(key);
    if (cached !== undefined) {
      this.set(nodeId, { ports: cached, loading: false, failed: false });
      return;
    }
    const prev = this.get(nodeId);
    this.set(nodeId, { ports: prev.ports, loading: true, failed: false });
    this.timers.set(
      nodeId,
      this.setTimer(() => {
        this.timers.delete(nodeId);
        void this.run(nodeId, key, typeId, config ?? {});
      }, this.delay),
    );
  }

  private async run(nodeId: string, key: string, typeId: string, config: unknown): Promise<void> {
    try {
      const ports = await this.resolveFn(typeId, config);
      this.cache.set(key, ports);
      if (this.want.get(nodeId) !== key) return; // 더 새 요청이 있음: 이 응답은 버린다
      this.set(nodeId, { ports, loading: false, failed: false });
    } catch {
      if (this.want.get(nodeId) !== key) return;
      this.set(nodeId, { ports: this.get(nodeId).ports, loading: false, failed: true });
    }
  }

  /** 더 이상 없는 노드 정리. */
  retain(nodeIds: ReadonlySet<string>): void {
    for (const id of [...this.want.keys()]) {
      if (nodeIds.has(id)) continue;
      this.want.delete(id);
      const t = this.timers.get(id);
      if (t !== undefined) this.clearTimer(t);
      this.timers.delete(id);
      if (this.entries.has(id)) {
        const next = new Map(this.entries);
        next.delete(id);
        this.entries = next;
      }
    }
  }

  dispose(): void {
    for (const t of this.timers.values()) this.clearTimer(t);
    this.timers.clear();
    this.listeners.clear();
  }
}
