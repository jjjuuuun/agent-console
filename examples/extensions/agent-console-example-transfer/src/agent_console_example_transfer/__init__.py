"""agent-console-example-transfer: 정의를 JSON 파일 하나로 내보내기(X8)·가져오기(X16).

내보내기 서비스(`agent_console_exports`)에는 entry point `agent_console.exporters`로,
가져오기 서비스(`agent_console_imports`)에는 `agent_console.import_sources`로만 등록된다.
서버 모듈은 import하지 않는다. 형식 이름·필드 이름·파일 이름은 옵션 데이터
(`data/defaults.json` + 설치자 옵션)다.

공개 API:
    - 형식 id: ``FORMAT_ID``(= 두 entry point 이름)
    - 형식 설정: ``BundleFormat``·``BundleFields``, ``load_format(options)``,
      ``default_format_data()``
    - 파일 쓰기·읽기(순수): ``BundleEntry``, ``dump_bundle``, ``read_bundle``,
      경고 코드 ``TransferIssueCodes``
    - 내보내기: ``JsonBundleExporter``, 공장 ``json_bundle_exporter(options)``,
      요청 옵션 ``OPTIONS_SCHEMA``
    - 가져오기: ``JsonBundleSource``, 공장 ``json_bundle_sources(ctx)``
"""

from agent_console_example_transfer._exporter import (
    OPTIONS_SCHEMA,
    JsonBundleExporter,
    json_bundle_exporter,
)
from agent_console_example_transfer._format import (
    FORMAT_ID,
    BundleEntry,
    BundleFields,
    BundleFormat,
    TransferIssueCodes,
    default_format_data,
    dump_bundle,
    load_format,
    read_bundle,
)
from agent_console_example_transfer._source import JsonBundleSource, json_bundle_sources

__all__ = [
    "FORMAT_ID",
    "OPTIONS_SCHEMA",
    "BundleEntry",
    "BundleFields",
    "BundleFormat",
    "JsonBundleExporter",
    "JsonBundleSource",
    "TransferIssueCodes",
    "default_format_data",
    "dump_bundle",
    "json_bundle_exporter",
    "json_bundle_sources",
    "load_format",
    "read_bundle",
]
