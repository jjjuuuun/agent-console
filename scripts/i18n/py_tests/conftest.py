"""공용 픽스처: 가짜 패키지 두 개를 가진 임시 저장소."""

from __future__ import annotations

from pathlib import Path

import pytest
from i18n_testkit import Repo


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)
