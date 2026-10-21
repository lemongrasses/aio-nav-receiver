from __future__ import annotations

from typing import Iterator

import pytest

from aio_receiver import i18n


@pytest.fixture(autouse=True)
def chinese() -> Iterator[None]:
    """Tests read the Chinese wording unless they switch; never depend on the machine's language."""
    i18n.set_language("zh-TW")
    yield
    i18n.set_language("zh-TW")
