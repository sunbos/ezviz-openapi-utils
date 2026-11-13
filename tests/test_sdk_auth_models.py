import importlib
import importlib.util

import pytest


@pytest.fixture
def auth():
    assert importlib.util.find_spec("ezviz_unified.auth_models") is not None, "Auth models missing"
    return importlib.import_module("ezviz_unified.auth_models")


def test_china_defaults_and_millisecond_conversion(auth):
    region = auth.RegionConfig.china()
    token = auth.parse_token(
        {"accessToken": "PRIVATE", "expireTime": 2_000_000}, region=region, now=1000.0
    )
    assert region.scope == "domestic"
    assert token.expires_at == 2000.0
    assert token.refresh_at == 1940.0
    assert token.api_base_url == "https://open.ys7.com"
    assert token.value == "PRIVATE" and "PRIVATE" not in repr(token)


def test_short_lifetime_does_not_cause_immediate_refresh(auth):
    token = auth.parse_token(
        {"accessToken": "TOKEN", "expireTime": 1_030_000},
        region=auth.RegionConfig.china(),
        now=1000.0,
    )
    assert token.expires_at == 1030 and token.refresh_at == 1015


def test_overseas_token_binds_to_returned_region(auth):
    region = auth.RegionConfig.overseas()
    assert region.auth_base_url == "https://open.ezvizlife.com"
    token = auth.parse_token(
        {
            "accessToken": "TOKEN",
            "expireTime": 2_000_000,
            "areaDomain": "https://isgpopen.ezviz.com/",
        },
        region=region,
        now=1000,
    )
    assert token.api_base_url == "https://isgpopen.ezviz.com"


def test_overseas_without_route_fails_unless_explicitly_configured(auth):
    from ezviz_unified import ProtocolError

    data = {"accessToken": "TOKEN", "expireTime": 2_000_000}
    with pytest.raises(ProtocolError):
        auth.parse_token(data, region=auth.RegionConfig.overseas(), now=1000)
    token = auth.parse_token(
        data, region=auth.RegionConfig.overseas(api_base_url="https://isgpopen.ezviz.com"), now=1000
    )
    assert token.api_base_url == "https://isgpopen.ezviz.com"


@pytest.mark.parametrize(
    "url",
    [
        "http://isgpopen.ezviz.com",
        "https://evil.example",
        "https://isgpopen.ezviz.com.evil.example",
        "https://user:secret@isgpopen.ezviz.com",
        "https://isgpopen.ezviz.com/path",
        "https://isgpopen.ezviz.com?key=x",
    ],
)
def test_invalid_overseas_config_is_rejected(auth, url):
    with pytest.raises(ValueError):
        auth.RegionConfig.overseas(auth_base_url=url)


def test_region_mismatch_does_not_override_explicit_route(auth):
    from ezviz_unified import ProtocolError

    with pytest.raises(ProtocolError):
        auth.parse_token(
            {
                "accessToken": "TOKEN",
                "expireTime": 2_000_000,
                "areaDomain": "https://iusopen.ezvizlife.com",
            },
            region=auth.RegionConfig.overseas(api_base_url="https://isgpopen.ezviz.com"),
            now=1000,
        )


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"accessToken": "", "expireTime": 2_000_000},
        {"accessToken": "TOKEN", "expireTime": True},
        {"accessToken": "TOKEN", "expireTime": "2000000"},
        {"accessToken": "TOKEN", "expireTime": 999_000},
    ],
)
def test_malformed_or_expired_token_is_protocol_error(auth, data):
    from ezviz_unified import ProtocolError

    with pytest.raises(ProtocolError):
        auth.parse_token(data, region=auth.RegionConfig.china(), now=1000)


def test_untrusted_returned_domain_is_rejected_without_echoing_secrets(auth):
    from ezviz_unified import ProtocolError

    with pytest.raises(ProtocolError) as caught:
        auth.parse_token(
            {
                "accessToken": "PRIVATE_TOKEN",
                "expireTime": 2_000_000,
                "areaDomain": "https://user:PRIVATE_KEY@evil.example",
            },
            region=auth.RegionConfig.overseas(),
            now=1000,
        )
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("skew", [-1, True, float("inf"), float("nan")])
def test_invalid_refresh_skew_is_rejected(auth, skew):
    with pytest.raises(ValueError):
        auth.parse_token(
            {"accessToken": "TOKEN", "expireTime": 2_000_000},
            region=auth.RegionConfig.china(),
            now=1000,
            refresh_skew=skew,
        )
