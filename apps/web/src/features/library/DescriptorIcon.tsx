import { Icon } from "@agent-console/ui";

/** 디스크립터 `ui_hints.icon`(레지스트리 이름 또는 짧은 텍스트)과 제목으로 아이콘을 그린다. 없으면 제목 첫 글자. */
export function DescriptorIcon({ hint, title, size = 16 }: { hint?: string | null | undefined; title: string; size?: number }) {
  const name = hint ?? undefined;
  return <Icon {...(name === undefined ? {} : { name })} fallbackText={name && name.trim() !== "" ? name : title} size={size} />;
}
