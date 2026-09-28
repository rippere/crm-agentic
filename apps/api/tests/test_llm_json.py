import json

import pytest

from app.services.llm_json import loads_llm_json


def test_plain_json():
    assert loads_llm_json('{"insight": "ok"}') == {"insight": "ok"}


def test_json_fence_as_returned_by_haiku():
    raw = '```json\n{"insight": "Pipeline is healthy."}\n```'
    assert loads_llm_json(raw) == {"insight": "Pipeline is healthy."}


def test_bare_fence_and_whitespace():
    assert loads_llm_json('  ```\n[1, 2]\n```  \n') == [1, 2]


def test_unterminated_fence():
    assert loads_llm_json('```json\n{"a": 1}') == {"a": 1}


@pytest.mark.parametrize("raw", ["", "```json\n```", "not json"])
def test_invalid_still_raises_json_decode_error(raw):
    with pytest.raises(json.JSONDecodeError):
        loads_llm_json(raw)
