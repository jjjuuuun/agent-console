"""agent-console-resources: 리소스 종류(X14) 등록과 실행 묶음 조립(design §R12).

종류 이름·칸 이름은 이 패키지에 없다. 종류는 entry point(`agent_console.resource_types`)·
명시 모듈·선언형 데이터(`resource-types/*.yaml`)로 들어온다.

공개 API:
    - 인터페이스: ``ResourceType``(``descriptor``·``validate``·``contribute``), ``Contribution``
      (``fallback`` = 받지 않는 칸 대신 쓸 기여), ``ContributeContext``,
      ``ResourceLookup``(정의·본문 조회), 선택 능력 ``FileContentLookup``(``read_files``,
      여러 파일 본문), ``InMemoryResources``, ``Content``, ``ContentFiles``.
    - 구현 도우미: ``SchemaResourceType``(config_schema 검사 베이스), ``effective_resource``,
      ``content_text``, ``is_secret_ref``·``find_plain_secrets``·``find_schema_plain_secrets``·
      ``PLAIN_SECRET``(`resource.plain_secret`)·``SECRET_REF_PREFIX``·
      ``SECRET_REF_PATTERN``, ``SECRET_SCHEMA_KEY``(`x-secret`), ``validate_config``·
      ``check_config_schema``·``ConfigViolation``·``InvalidConfigSchemaError``,
      ``render_template``·``fill_value``.
    - 로딩: ``RESOURCE_TYPES_GROUP``, ``new_resource_types()``,
      ``load_resource_types(registry, ...)``,
      ``as_resource_type``, ``list_descriptors``, 선언형 ``load_declarative_types(dir, registry)``,
      ``declarative_type_from_data``, ``DeclarativeResourceType``, ``DeclarativeTypeSpec``,
      ``ContributionSpec``, ``DeclarativeTypeError``.
    - 첨부 병합 전략: ``ATTACHMENT_STRATEGY``(``keyed_attachments``), ``PREPEND_STRATEGY``,
      ``keyed_attachments_strategy(slot_key_of)``, ``attachment_slot_key(types, resources)``,
      ``prepend``, ``register_resource_strategies(table, ...)``, ``resource_strategies(...)``.
    - 묶음: ``compose_bundle(layers, *, types, resources, accepted_slots, strategies, slot_notes)``,
      이슈 코드 ``SLOT_UNSUPPORTED``·``SLOT_FALLBACK``,
      ``resolve_attachments``, ``build_bundle``, ``placed_from_resolved``, ``unsupported_slots``,
      ``AttachmentLayer``, ``PlacedAttachment``, ``ComposedBundle``.
    - 저장 전 검사: ``validate_resource(resource, types)``(값 없는 메시지),
      ``validate_attachment(attachment, *, types, resources, path, secret_rules=)``(첨부 config
      덮어쓰기, 리소스가 없으면 ``ac-secret-rules`` 의심 규칙),
    - 표시용 가리기(`x-secret` 평문): ``mask_plain_secrets(value, schema)``, ``mask_resource``,
      ``mask_attachment``, ``MaskedResources``(ResourceLookup 감싸기), ``SECRET_MASK``,
      ``scrub_issue_values(issues, config)``.
"""

from agent_console_resources._attachments import (
    ATTACHMENT_STRATEGY,
    PREPEND_STRATEGY,
    AttachmentKeyFn,
    attachment_slot_key,
    keyed_attachments_strategy,
    prepend,
    register_resource_strategies,
    resource_strategies,
)
from agent_console_resources._base import (
    PLAIN_SECRET,
    SECRET_REF_PATTERN,
    SECRET_REF_PREFIX,
    SECRET_SCHEMA_KEY,
    SchemaResourceType,
    content_text,
    effective_resource,
    find_plain_secrets,
    find_schema_plain_secrets,
    is_secret_ref,
)
from agent_console_resources._bundle import (
    SLOT_FALLBACK,
    SLOT_UNSUPPORTED,
    AttachmentLayer,
    ComposedBundle,
    PlacedAttachment,
    build_bundle,
    compose_bundle,
    placed_from_resolved,
    resolve_attachments,
    unsupported_slots,
)
from agent_console_resources._declarative import (
    DECLARATIVE_SUFFIXES,
    ContributionSpec,
    DeclarativeResourceType,
    DeclarativeTypeError,
    DeclarativeTypeSpec,
    declarative_type_from_data,
    load_declarative_types,
)
from agent_console_resources._interfaces import (
    Content,
    ContentFiles,
    ContributeContext,
    Contribution,
    FileContentLookup,
    InMemoryResources,
    ResourceLookup,
    ResourceType,
)
from agent_console_resources._loading import (
    RESOURCE_TYPES_GROUP,
    as_resource_type,
    list_descriptors,
    load_resource_types,
    new_resource_types,
)
from agent_console_resources._mask import (
    SECRET_MASK,
    MaskedResources,
    mask_attachment,
    mask_plain_secrets,
    mask_resource,
)
from agent_console_resources._schema import (
    ConfigViolation,
    InvalidConfigSchemaError,
    check_config_schema,
    validate_config,
)
from agent_console_resources._template import (
    DEFAULT_MAX_RENDER_CHARS,
    fill_value,
    render_template,
)
from agent_console_resources._validate import (
    OVERRIDE_FIELD,
    OVERRIDE_SECRET_SUSPECTED,
    scrub_issue_values,
    validate_attachment,
    validate_resource,
)

__all__ = [
    "ATTACHMENT_STRATEGY",
    "DECLARATIVE_SUFFIXES",
    "DEFAULT_MAX_RENDER_CHARS",
    "OVERRIDE_FIELD",
    "OVERRIDE_SECRET_SUSPECTED",
    "PLAIN_SECRET",
    "PREPEND_STRATEGY",
    "RESOURCE_TYPES_GROUP",
    "SECRET_MASK",
    "SECRET_REF_PATTERN",
    "SECRET_REF_PREFIX",
    "SECRET_SCHEMA_KEY",
    "SLOT_FALLBACK",
    "SLOT_UNSUPPORTED",
    "AttachmentKeyFn",
    "AttachmentLayer",
    "ComposedBundle",
    "ConfigViolation",
    "Content",
    "ContentFiles",
    "ContributeContext",
    "Contribution",
    "ContributionSpec",
    "DeclarativeResourceType",
    "DeclarativeTypeError",
    "DeclarativeTypeSpec",
    "FileContentLookup",
    "InMemoryResources",
    "InvalidConfigSchemaError",
    "MaskedResources",
    "PlacedAttachment",
    "ResourceLookup",
    "ResourceType",
    "SchemaResourceType",
    "as_resource_type",
    "attachment_slot_key",
    "build_bundle",
    "check_config_schema",
    "compose_bundle",
    "content_text",
    "declarative_type_from_data",
    "effective_resource",
    "fill_value",
    "find_plain_secrets",
    "find_schema_plain_secrets",
    "is_secret_ref",
    "keyed_attachments_strategy",
    "list_descriptors",
    "load_declarative_types",
    "load_resource_types",
    "mask_attachment",
    "mask_plain_secrets",
    "mask_resource",
    "new_resource_types",
    "placed_from_resolved",
    "prepend",
    "register_resource_strategies",
    "render_template",
    "resolve_attachments",
    "resource_strategies",
    "scrub_issue_values",
    "unsupported_slots",
    "validate_attachment",
    "validate_config",
    "validate_resource",
]
