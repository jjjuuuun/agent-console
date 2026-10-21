"""Alembic 환경. 연결은 `migrate.py`가 `config.attributes["connection"]`으로 넘겨 준다.

legacy 계보만 `schema.metadata`와 비교한다(`compare_type`). 모듈 브랜치는 자기 테이블만 알기 때문에
비교 대상이 없다. 버전 테이블은 `config.attributes["version_table"]`.
"""

from alembic import context

from agent_console_store.schema import metadata

config = context.config
connection = config.attributes["connection"]

context.configure(
    connection=connection,
    target_metadata=metadata if config.attributes.get("legacy", True) else None,
    compare_type=True,
    version_table=config.attributes.get("version_table", "alembic_version"),
)
with context.begin_transaction():
    context.run_migrations()
