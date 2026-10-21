import type { Resource, ResourceTypeDescriptor } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { ConfigTab } from "./ConfigTab";
import { ContentTab } from "./ContentTab";
import { MultiFileTab } from "./MultiFileTab";
import { editorLanguageOf, isMultiFile, mediaTypeOf, toConfigErrors, type ResourceDoc } from "./resourceLogic";

/** 편집 콜백: 값 또는 "현재 → 다음" 함수(늦게 도착한 입력이 낡은 초안을 되살리지 못하게 한다). */
export type ResourceDocUpdate = ResourceDoc | ((current: ResourceDoc) => ResourceDoc);

export interface ResourceEditorFormProps {
  /** 이 종류의 디스크립터. 모르는 종류(서버가 목록에서 뺐음)면 undefined: 설정은 JSON 읽기 전용으로 보인다 */
  descriptor: ResourceTypeDescriptor | undefined;
  doc: ResourceDoc;
  onChange: (next: ResourceDocUpdate) => void;
  /** 저장이 거부된 사유(필드 오류, JSON Pointer 경로) */
  errors?: readonly FormError[];
  disabled?: boolean;
  /** 어느 부분을 그릴지: 본문(문서·파일 트리), 설정 폼, 둘 다(서랍처럼 탭이 없을 때, 본문이 있는 종류만 둘 다) */
  part: "content" | "config" | "all";
  /** 본문 편집기 안 Ctrl+S */
  onSave?: () => void;
  /** 설정 부분 앞에 붙는 제목(`part="all"`에서 구역 구분) */
  configHeading?: string;
  /** 본문 부분 앞에 붙는 제목(`part="all"`) */
  contentHeading?: string;
}

/**
 * 리소스 편집 폼: 종류 디스크립터가 정하는 편집기(문서형 = 텍스트 편집기, 설정형 = 스키마 폼, 여러 파일형 = 파일 트리)를
 * 그린다. 리소스 화면의 [내용]·[설정] 탭과 팀 편집기의 `CreateDefinitionDrawer`가 같은 컴포넌트를 쓴다.
 * 서버·저장을 모른다(문서와 콜백만).
 */
export function ResourceEditorForm({ descriptor, doc, onChange, errors = [], disabled = false, part, onSave, configHeading, contentHeading }: ResourceEditorFormProps) {
  const { resource } = doc;
  const hasContent = descriptor === undefined ? resource.content != null : descriptor.content != null;
  const showContent = part !== "config" && (part === "content" || hasContent);
  const showConfig = part !== "content";
  const mediaType = mediaTypeOf(resource, descriptor);
  const patchResource = (patch: Partial<Resource>) => onChange((cur) => ({ ...cur, resource: { ...cur.resource, ...patch } }));
  const setConfig = (config: Record<string, unknown>) =>
    onChange((cur) => {
      const next = { ...cur.resource } as Record<string, unknown>;
      if (Object.keys(config).length === 0) delete next["config"];
      else next["config"] = config;
      return { ...cur, resource: next as unknown as Resource };
    });
  const save = onSave ?? (() => {});

  const content = !showContent ? null : isMultiFile(descriptor) ? (
    <MultiFileTab
      files={doc.files ?? []}
      originFiles={doc.origin.files ?? []}
      onChange={(files) => onChange((cur) => ({ ...cur, files }))}
      errors={doc.fileErrors ?? {}}
      onDismissError={(path) =>
        onChange((cur) => {
          const left = { ...(cur.fileErrors ?? {}) };
          delete left[path];
          const { fileErrors: _old, ...others } = cur;
          void _old;
          return Object.keys(left).length === 0 ? others : { ...others, fileErrors: left };
        })
      }
      onSave={save}
      disabled={disabled}
    />
  ) : (
    <ContentTab
      text={doc.text ?? ""}
      onChange={(text) => onChange((cur) => ({ ...cur, text }))}
      language={editorLanguageOf(descriptor)}
      mediaTypes={descriptor?.content?.media_types ?? []}
      mediaType={mediaType}
      onMediaTypeChange={(next) => patchResource({ content: { ...(resource.content ?? { file: "" }), media_type: next } })}
      onSave={save}
    />
  );

  const config = !showConfig ? null : descriptor === undefined ? (
    <pre className="ac-pre app-json">{JSON.stringify(resource, null, 2)}</pre>
  ) : (
    <ConfigTab descriptor={descriptor} value={(resource.config ?? {}) as Record<string, unknown>} onChange={setConfig} errors={toConfigErrors([...errors])} disabled={disabled} />
  );

  if (part !== "all") return <>{content ?? config}</>;
  return (
    <div className="lib-form">
      {content === null ? null : (
        <section className="res-editor-part" aria-label={contentHeading}>
          {contentHeading ? <h3 className="app-block-title">{contentHeading}</h3> : null}
          {content}
        </section>
      )}
      {config === null ? null : (
        <section className="res-editor-part" aria-label={configHeading}>
          {configHeading ? <h3 className="app-block-title">{configHeading}</h3> : null}
          {config}
        </section>
      )}
    </div>
  );
}
