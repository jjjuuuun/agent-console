import { useEffect, useState } from "react";
import { Button, Icon } from "@agent-console/ui";

const COPIED_MS = 1500;

export interface CopyButtonProps {
  /** 복사할 텍스트 */
  text: string;
  /** 평소 버튼 글자 */
  label: string;
  /** 복사한 직후 글자(스크린리더에도 알린다) */
  copiedLabel: string;
}

/** 텍스트를 클립보드에 복사하는 작은 버튼. 복사하면 잠깐 완료 글자로 바뀐다. */
export function CopyButton({ text, label, copiedLabel }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const h = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(h);
  }, [copied]);
  return (
    <Button
      size="sm"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => setCopied(true), () => {});
      }}
    >
      <Icon name={copied ? "check" : "copy"} />
      <span role="status">{copied ? copiedLabel : label}</span>
    </Button>
  );
}
