#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EZVIZ OpenAPI OAuth Module Tests

This module provides unit tests for the OAuth authentication functionality
of the EZVIZ OpenAPI platform. Tests cover token acquisition, validation,
and error handling scenarios.

Test Requirements:
- Set EZVIZ_APP_KEY and EZVIZ_APP_SECRET in .env file
- Tests validate token lifecycle and error handling
- Supports multiple regional API endpoints

Author: SunBo <1443584939@qq.com>
License: MIT
"""

import os
import pytest
from dotenv import load_dotenv
from src.ezviz_openapi_utils.oauth import AccessToken, EZVIZAuthError

# 在模块加载时，自动从项目根目录的 .env 文件中加载环境变量
load_dotenv()

# 从加载的环境变量中获取密钥
APP_KEY = os.getenv("EZVIZ_APP_KEY")
APP_SECRET = os.getenv("EZVIZ_APP_SECRET")

# 使用 pytest.mark.skipif 装饰器：
# 如果 APP_KEY 或 APP_SECRET 未设置（即 all(...) 为 False），
# 则自动跳过下面的测试，并显示指定的 reason。
@pytest.mark.skipif(not all([APP_KEY, APP_SECRET]), reason="环境变量 EZVIZ_APP_KEY 或 EZVIZ_APP_SECRET 未在 .env 文件中设置")
def test_real_token_acquisition():
    """
    集成测试：使用真实的凭据从萤石开放平台获取 accessToken。

    这个测试会发起一个真实的外部 HTTP 请求。

    前置条件:
    1. 项目根目录下存在 .env 文件。
    2. .env 文件中定义了有效的 EZVIZ_APP_KEY 和 EZVIZ_APP_SECRET。
    """
    try:
        # 使用从 .env 文件加载的凭据实例化 AccessToken，这将触发一个真实的 HTTP 请求
        token_response = AccessToken(app_key=APP_KEY, app_secret=APP_SECRET, region="cn")

        # 打印获取到的 token 响应对象，以便直观查看
        print(f"\n【真实请求成功】响应详情: {token_response}")

        # 1. 断言请求成功，返回码应为 "200"
        assert token_response.code == "200", f"API 请求失败，返回码: {token_response.code}，消息: {token_response.msg}"

        # 2. 断言响应中的 data 对象不为空
        assert token_response.data is not None, "API 响应中缺少 'data' 字段"

        # 3. 断言成功获取了 accessToken，且它是一个非空的字符串
        assert token_response.data.access_token is not None
        assert isinstance(token_response.data.access_token, str)
        assert len(token_response.data.access_token) > 0, "获取到的 accessToken 为空字符串"

    except EZVIZAuthError as e:
        # 如果发生认证错误（例如，密钥无效），测试将失败并打印详细的错误信息
        pytest.fail(f"获取真实 token 时发生认证错误，请检查您的 appKey 和 appSecret 是否正确: {e}")
    except Exception as e:
        # 捕获其他所有异常（如网络连接问题），并让测试失败
        pytest.fail(f"获取真实 token 时发生未知错误: {e}")
