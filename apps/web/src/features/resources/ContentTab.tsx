import { useEffect, useState } from "react";
import { Markdown } from "@agent-console/chat";
import type { TextEditorStatus } from "@agent-console/text-editor";
import { LazyTextEditor } from "../library";
import { Banner, useShortcuts } from "@agent-console/ui";
import { resourceMessages as t } from "./messages";
import { MAX_EDIT_BYTES, WARN_BYTES } from "./resourceLogic";

export interface ContentTabProps {
  text: string;
  onChange: (next: string) => void;
  /** `content.editor` 어휘(markdown·html·json·text, 모르면 text) */
  language: string;
  mediaTypes: readonly string[];
  mediaType: string;
  onMediaTypeChange: (next: string) => void;
  /** 저장(편집기 안 Ctrl+S) */
  onSave: () => void;
  readOnly?: boolean;
}

const PREVIEW_LANGUAGE = "markdown";
const HTML_LANGUAGE = "html";
const JSON_LANGUAGE = "json";

function byteSize(text: string): number {
  return new TextEncoder().encode(text).length;
}

/** 문서형 리소스 본문 편집: CodeMirror 편집기 + 마크다운 미리보기 분할 + 상태 줄. 저장·서버를 모른다. */
export function ContentTab({ text, onChange, language, mediaTypes, mediaType, onMediaTypeChange, onSave, readOnly }: ContentTabProps) {
  const [preview, setPreview] = useState(true);
  const [status, setStatus] = useState<TextEditorStatus>({ line: 1, col: 1, chars: text.length });
  const bytes = byteSize(text);
  const canPreview = language === PREVIEW_LANGUAGE;

  useShortcuts([{ id: "resources.preview", scope: "resources", keys: "Mod+Shift+P", titleKey: "shortcuts.libTogglePreview", run: () => setPreview((v) => !v) }]);
  // 좁은 화면에서는 편집기와 미리보기를 번갈아 본다(폭 < 1100)
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.innerWidth < 1100);
  useEffect(() => {
    const on = () => setNarrow(window.innerWidth < 1100);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);

  return (
    <div className="res-content">
      <div className="res-content-bar">
        {mediaTypes.length > 1 ? (
          <label className="app-check">
            <span>{t.content.mediaType}</span>
            <select value={mediaType} onChange={(e) => onMediaTypeChange(e.target.value)} disabled={readOnly}>
              {!mediaTypes.includes(mediaType) ? <option value={mediaType}>{mediaType}</option> : null}
              {mediaTypes.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {canPreview ? (
          <label className="app-check">
            <input type="checkbox" checked={preview} onChange={(e) => setPreview(e.target.checked)} aria-keyshortcuts="Control+Shift+P" />
            {t.content.preview}
          </label>
        ) : null}
      </div>
      {bytes > MAX_EDIT_BYTES ? <Banner tone="warning">{t.content.tooLarge}</Banner> : bytes > WARN_BYTES ? <Banner tone="info">{t.content.large}</Banner> : null}
      {language === JSON_LANGUAGE && status.parseError !== undefined ? (
        <Banner tone="warning">
          {t.content.jsonInvalid} <span className="lib-mono">{status.parseError}</span>
        </Banner>
      ) : null}
      {language === HTML_LANGUAGE ? <p className="app-muted lib-field-note">{t.content.noHtmlPreview}</p> : null}
      <div className="res-content-split" data-preview={canPreview && preview ? "true" : "false"} data-narrow={narrow ? "true" : "false"}>
        <div className="res-editor">
          <LazyTextEditor
            value={text}
            onChange={onChange}
            language={language}
            ariaLabel={t.content.editorLabel}
            onSave={onSave}
            maxBytes={MAX_EDIT_BYTES}
            onStatus={setStatus}
            height="fill"
            readOnly={readOnly === true}
            messages={{ tooLarge: t.content.tooLargeShort }}
          />
        </div>
        {canPreview && preview ? (
          <section className="res-preview" aria-label={t.content.preview}>
            {text.trim() === "" ? <p className="app-muted">{t.content.previewEmpty}</p> : <Markdown text={text} />}
          </section>
        ) : null}
      </div>
      <div className="res-statusline app-muted" role="status">
        {t.content.status(status.line, status.col, text.length, mediaType)}
      </div>
    </div>
  );
}
