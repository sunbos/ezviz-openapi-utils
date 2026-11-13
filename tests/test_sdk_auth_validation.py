import pytest

from ezviz_unified import ProtocolError
from ezviz_unified.auth_models import RegionConfig, parse_token


@pytest.mark.parametrize(
    "url",
    [
        "https://isgpopen.ezviz.com:PRIVATE_PORT",
        "https://isgpopen.ezviz.com?",
        "https://isgpopen.ezviz.com#",
        "https://isgpopen..ezviz.com",
        "https://isgpopen.ezviz.com:444",
        "https://isgpopen.ezviz.com\n",
    ],
)
def test_bad_origin_has_no_sensitive_exception_chain(url):
    with pytest.raises(ValueError) as caught:
        RegionConfig.overseas(auth_base_url=url)
    error = caught.value
    while error is not None:
        assert "PRIVATE" not in str(error)
        error = error.__context__


def test_bad_server_origin_has_no_sensitive_exception_chain():
    with pytest.raises(ProtocolError) as caught:
        parse_token(
            {
                "accessToken": "TOKEN",
                "expireTime": 2_000_000,
                "areaDomain": "https://isgpopen.ezviz.com:PRIVATE_PORT",
            },
            region=RegionConfig.overseas(),
            now=1000,
        )
    error = caught.value
    while error is not None:
        assert "PRIVATE" not in str(error)
        error = error.__context__


def test_extreme_expiry_is_protocol_error():
    with pytest.raises(ProtocolError):
        parse_token(
            {"accessToken": "TOKEN", "expireTime": 10**500}, region=RegionConfig.china(), now=1000
        )


def test_default_port_is_normalized_and_domestic_cannot_cross_region():
    region = RegionConfig.overseas(auth_base_url="https://ISGPOPEN.EZVIZ.COM:443/")
    assert region.auth_base_url == "https://isgpopen.ezviz.com"
    with pytest.raises(ProtocolError):
        parse_token(
            {
                "accessToken": "TOKEN",
                "expireTime": 2_000_000,
                "areaDomain": "https://isgpopen.ezviz.com",
            },
            region=RegionConfig.china(),
            now=1000,
        )
