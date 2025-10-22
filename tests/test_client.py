#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EZVIZ OpenAPI Client Module Tests

This module provides unit and integration tests for the Client class functionality.
Tests cover client initialization, token management, session handling, and API request
processing capabilities of the EZVIZ OpenAPI platform.

Test Requirements:
- Set EZVIZ_APP_KEY and EZVIZ_APP_SECRET in .env file
- Tests validate client lifecycle and error handling
- Covers automatic token refresh mechanisms

Author: SunBo <1443584939@qq.com>
License: MIT
"""

import os
import pytest
from dotenv import load_dotenv
from src.ezviz_openapi_utils.client import Client, EZVIZAuthError
from src.ezviz_openapi_utils.api import EZVIZOpenAPI
from src.ezviz_openapi_utils.exceptions import EZVIZAPIError

# 加载 .env 文件中的环境变量
load_dotenv()
APP_KEY = os.getenv("EZVIZ_APP_KEY")
APP_SECRET = os.getenv("EZVIZ_APP_SECRET")

# Pytest 标记：如果 .env 文件中缺少密钥，则跳过此文件中的所有测试
pytestmark = pytest.mark.skipif(
    not all([APP_KEY, APP_SECRET]),
    reason="环境变量 EZVIZ_APP_KEY 或 EZVIZ_APP_SECRET 未在 .env 文件中设置"
)

def test_real_client_initialization_success():
    """
    集成测试：验证 Client 能否使用真实的有效凭据成功初始化。
    """
    try:
        client = Client(app_key=APP_KEY, app_secret=APP_SECRET)
        # 打印部分获取到的 token 以供确认
        print(f"\n【客户端初始化成功】获取到的Token: at.{client.access_token.split('.')[-1][:20]}...")
        assert client._access_token.code == "200"
        assert client.access_token is not None
        assert len(client.access_token) > 0
    except EZVIZAuthError as e:
        pytest.fail(f"客户端初始化失败，请检查您的凭据是否有效: {e}")

def test_real_client_initialization_failure():
    """
    集成测试：验证 Client 在使用无效凭据时是否按预期抛出认证错误。
    """
    with pytest.raises(EZVIZAuthError) as excinfo:
        # 使用一组明显无效的凭据
        Client(app_key="invalid-app-key", app_secret="invalid-app-secret")

    # 打印捕获到的错误信息
    print(f"\n【客户端初始化失败测试】成功捕获到预期的认证错误: {excinfo.value}")

    # 断言错误码是预期的“无效凭据”错误码之一
    assert excinfo.value.code in ["10017", "10001"]

def test_real_authenticated_request():
    """
    集成测试：验证一个初始化成功的 Client 实例能否成功发起需要认证的真实 API 请求。
    """
    try:
        client = Client(app_key=APP_KEY, app_secret=APP_SECRET)
        api = EZVIZOpenAPI(client)

        # 我们调用一个常见的、只读的 API：获取设备列表
        # 这是萤石开放平台的一个标准接口，用于测试认证是否成功
        response = api.list_devices_by_page(page_start=0, page_size=10)

        # 打印 API 响应以便查看
        print(f"\n【认证请求成功】API 响应: {response}")

        # 验证响应码为 "200"，表示业务操作成功
        assert response.get("code") == "200"

    except (EZVIZAuthError, EZVIZAPIError) as e:
        pytest.fail(f"客户端在初始化阶段或API调用时失败，无法进行认证请求测试: {e}")
    except Exception as e:
        pytest.fail(f"发起认证请求时发生未知错误: {e}")
