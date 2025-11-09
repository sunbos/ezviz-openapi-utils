#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EZVIZ OpenAPI Client Module

This module provides the Client class for handling authentication and API requests
to the EZVIZ OpenAPI platform. It manages token lifecycle, session handling,
and automatic retry mechanisms for token expiration.

Author: SunBo <1443584939@qq.com>
License: MIT
"""

import requests
from typing import Any, Dict, Optional, cast

from .oauth import AccessToken, Region
from .exceptions import EZVIZAuthError, EZVIZAPIError

class Client:
    TOKEN_SUCCESS_CODE = "200"
    TOKEN_EXPIRED_CODE = "10002"  # 10002 是过期/异常码
    
    def __init__(self, app_key: str, app_secret: str, region: Region = "cn"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.region: Region = region
        self._session = requests.Session()

        self._access_token = AccessToken(self.app_key, self.app_secret, self.region)
        if self._access_token.code != self.TOKEN_SUCCESS_CODE:
            raise EZVIZAuthError(self._access_token.code, self._access_token.msg, "客户端初始化失败")

    @property
    def access_token(self) -> str:
        if self._access_token.code == self.TOKEN_EXPIRED_CODE:
            # 重新获取 token
            self._access_token = AccessToken(self.app_key, self.app_secret, self.region)
            if self._access_token.code != self.TOKEN_SUCCESS_CODE:
                raise EZVIZAuthError(self._access_token.code, self._access_token.msg,"重新获取 access_token 失败")
        return cast(str, self._access_token.data.access_token)

    @property
    def expire_time(self) -> int:
        return cast(int, self._access_token.data.expire_time)

    @property
    def area_domain(self) -> Optional[str]:
        return self._access_token.data.area_domain

    @property
    def code(self) -> str:
        return self._access_token.code

    @property
    def msg(self) -> str:
        return self._access_token.msg

    def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        执行HTTP请求的核心方法。
        自动附加access_token，并处理通用的API错误。
        """
        # 确保每次请求都使用最新的token
        access_token = self.access_token

        # 准备请求参数
        if method.upper() == 'GET':
            params = kwargs.get('params', {})
            params['accessToken'] = access_token
            kwargs['params'] = params
        else:  # POST, PUT, DELETE etc.
            data = kwargs.get('data', {})
            if isinstance(data, dict):
                data['accessToken'] = access_token
                kwargs['data'] = data

        try:
            response = self._session.request(method, url, **kwargs)
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as e:
            raise EZVIZAPIError("500", f"网络请求失败: {str(e)}", "网络错误")

        return result
