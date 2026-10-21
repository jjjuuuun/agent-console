import type { AvatarSpec } from "../messages/types";
import { avatarColorIndex } from "./util";

/** 에이전트 아바타(원형). 글자·색은 `avatar`(앱이 해석)가 우선이고, 없으면 이름 첫 글자 + id 해시 `--ac-cat-N`. */
export function Avatar({ agentId, name, size = 24, avatar }: { agentId: string; name: string; size?: number; avatar?: AvatarSpec | undefined }) {
  const text = avatar?.text && avatar.text !== "" ? avatar.text : (Array.from(name)[0] ?? "?");
  return (
    <span
      aria-hidden="true"
      data-avatar=""
      style={{
        width: size,
        height: size,
        flex: "none",
        borderRadius: "var(--ac-radius-full)",
        background: avatar?.color && avatar.color !== "" ? avatar.color : `var(--ac-cat-${avatarColorIndex(agentId)})`,
        color: "var(--ac-text-on-accent)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: size < 20 ? "11px" : "var(--ac-text-xs, 12px)",
        fontWeight: 600,
        overflow: "hidden",
      }}
    >
      {text}
    </span>
  );
}
