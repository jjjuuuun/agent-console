import { resolveAvatar } from "./avatarSpec";

/**
 * 에이전트 아바타. 글자·색은 `resolveAvatar`(표시 설정 → 이름 첫 글자 + id 해시 색)가 정한다.
 * 색만으로 의미를 전하지 않는다(이름 텍스트가 항상 곁에 있다).
 */
export function Avatar({ id, name, attributes, size = 24 }: { id: string; name: string; attributes?: Readonly<Record<string, unknown>> | null | undefined; size?: number }) {
  const spec = resolveAvatar({ id, name, attributes });
  return (
    <span className="lib-avatar" style={{ width: size, height: size, background: spec.color, fontSize: Math.max(11, Math.round(size * 0.5)) }} aria-hidden="true">
      {spec.text}
    </span>
  );
}
