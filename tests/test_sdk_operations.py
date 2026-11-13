import dataclasses

import pytest

from ezviz_unified.operations import Operation


def test_operation_defaults_deny_replay_and_freeze_regions():
    regions = {"domestic"}
    operation = Operation("example", "POST", "/example", regions=regions)
    regions.add("overseas")
    assert operation.regions == {"domestic"}
    assert operation.read_only is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        operation.read_only = True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": " "},
        {"method": "post"},
        {"path": "https://evil.example"},
        {"path": "//evil.example"},
        {"path": "/path?"},
        {"path": "/path#"},
        {"path": "/p\nath"},
        {"path": "/p\\ath"},
        {"regions": set()},
        {"regions": {"unverified"}},
        {"token_location": "cookie"},
        {"read_only": 1},
    ],
)
def test_invalid_operation_is_rejected(kwargs):
    values = {"name": "example", "method": "GET", "path": "/example", **kwargs}
    with pytest.raises((ValueError, TypeError)):
        Operation(**values)
