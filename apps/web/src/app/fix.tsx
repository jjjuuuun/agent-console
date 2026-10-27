import { useNavigate, useSearchParams } from "react-router";
import type { Fix, FixAction } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import { useRequiresPartition } from "../modules/ModulesContext";
import { DEFAULT_ROUTES, routeServing, type RouteDef } from "../shell/routeConfig";

/** 해결 버튼이 이동할 곳을 담는 주소 조각 이름(받는 화면이 `useFixTarget`으로 읽는다). */
export const FIX_PARAMS = { section: "section", focus: "focus", arrived: "fix" } as const;

/** 해결 버튼 하나를 주소로 푼 결과. */
export interface ResolvedFixAction {
  label: string;
  to: string;
}

/**
 * 해결 버튼의 대상 역할(`target.role`)을 라우트 설정에서 찾아 주소로 만든다. 역할을 맡은 라우트가 없으면 undefined.
 * `target.id`는 경로 뒤에 붙고, `target.section`·`focus`는 쿼리(`section`·`focus`)로 간다. 역할 이름은 코드에 없다(오류 데이터).
 */
export function fixActionTo(action: FixAction, routes: readonly RouteDef[] = DEFAULT_ROUTES): string | undefined {
  const route = routeServing(routes, action.target.role);
  if (route === undefined) return undefined;
  const base = action.target.id == null || action.target.id === "" ? route.path : `${route.path}/${encodeURIComponent(action.target.id)}`;
  const query = new URLSearchParams();
  if (action.target.section != null && action.target.section !== "") query.set(FIX_PARAMS.section, action.target.section);
  if (action.focus != null && action.focus !== "") query.set(FIX_PARAMS.focus, action.focus);
  // 대상 위치·필드가 없는 해결(예: 입구 없음)도 도착 화면이 "해결로 왔다"를 알 수 있게 표시를 붙인다(항목 id가 있을 때만)
  if (query.toString() === "" && base !== route.path) query.set(FIX_PARAMS.arrived, "1");
  const qs = query.toString();
  return qs === "" ? base : `${base}?${qs}`;
}

/** 오류·이슈의 `fix`를 이동 가능한 버튼 목록으로. 맡은 화면이 없거나 꺼진 기능이면 그 버튼을 뺀다. */
export function useResolvedFix(fix: Fix | null | undefined): ResolvedFixAction[] {
  const { unmet } = useRequiresPartition(DEFAULT_ROUTES);
  const out: ResolvedFixAction[] = [];
  for (const action of fix?.actions ?? []) {
    const route = routeServing(DEFAULT_ROUTES, action.target.role);
    if (route === undefined || unmet.includes(route)) continue;
    const to = fixActionTo(action);
    if (to !== undefined) out.push({ label: action.label, to });
  }
  return out;
}

export interface FixButtonsProps {
  fix: Fix | null | undefined;
  /** 이동 직전에 부를 콜백(다이얼로그 닫기 등) */
  onNavigate?: () => void;
  size?: "sm" | "md";
}

/** `fix.actions`를 버튼으로 그린다. 쓸 수 있는 버튼이 없으면 아무것도 그리지 않는다. */
export function FixButtons({ fix, onNavigate, size = "sm" }: FixButtonsProps) {
  if (fix == null || (fix.actions ?? []).length === 0) return null;
  return <FixButtonRow fix={fix} size={size} {...(onNavigate === undefined ? {} : { onNavigate })} />;
}

function FixButtonRow({ fix, onNavigate, size }: { fix: Fix; onNavigate?: () => void; size: "sm" | "md" }) {
  const navigate = useNavigate();
  const actions = useResolvedFix(fix);
  if (actions.length === 0) return null;
  return (
    <div className="app-fix-actions">
      {actions.map((a, i) => (
        <Button
          key={`${a.to}:${a.label}`}
          size={size}
          variant={i === 0 ? "primary" : "secondary"}
          onClick={() => {
            onNavigate?.();
            void navigate(a.to);
          }}
        >
          {a.label}
        </Button>
      ))}
    </div>
  );
}

/** 해결 버튼으로 열린 화면이 읽는 대상: `section`(화면 안 위치)·`focus`(폼 필드 JSON Pointer). */
export function useFixTarget(): { section: string | null; focus: string | null; arrived: boolean } {
  const [params] = useSearchParams();
  return { section: params.get(FIX_PARAMS.section), focus: params.get(FIX_PARAMS.focus), arrived: params.get(FIX_PARAMS.arrived) === "1" };
}

/** 포커스된 입력을 잠깐 강조한다(`data-fix-flash`, 기본 2초). 폼이 포커스를 옮긴 뒤 부른다. */
export function flashFocused(root: ParentNode | null = document, ms = 2000): void {
  const el = document.activeElement;
  if (!(el instanceof HTMLElement) || el === document.body || (root !== null && root !== document && !(root as Node).contains(el))) return;
  el.setAttribute("data-fix-flash", "true");
  el.scrollIntoView?.({ block: "center" });
  window.setTimeout(() => el.removeAttribute("data-fix-flash"), ms);
}

/** 요소 하나를 잠깐 강조한다(`data-fix-flash`, 기본 2초). 포커스와 무관하다. 취소 함수를 돌려준다. */
export function flashElement(el: HTMLElement, ms = 2000): () => void {
  el.setAttribute("data-fix-flash", "true");
  el.scrollIntoView?.({ block: "center" });
  const t = window.setTimeout(() => el.removeAttribute("data-fix-flash"), ms);
  return () => {
    window.clearTimeout(t);
    el.removeAttribute("data-fix-flash");
  };
}
