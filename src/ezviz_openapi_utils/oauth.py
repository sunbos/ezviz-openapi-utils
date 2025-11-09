#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EZVIZ OpenAPI OAuth Module

This module provides authentication and token management functionality for the EZVIZ
OpenAPI platform. It handles OAuth authentication flow, token refresh mechanisms,
and supports multiple regional API endpoints.

Author: SunBo <1443584939@qq.com>
License: MIT
"""

from typing import Literal, TypedDict, Union, cast
import requests
from .exceptions import EZVIZAuthError

# 1. 常量 (Constants)
# 定义已知错误码及其描述，便于维护和扩展
# 仅包含可能返回的错误码
ERROR_CODE_REMARKS = {
    '10001': "参数为空或格式不正确",
    '10005': "appKey被冻结",
    '10017': "确认appKey是否正确",
    '10030': "",
    '49999': "接口调用异常"
}

# 2. 类型定义 (Type Definitions)
Region = Literal["cn", "en", "eu", "us", "sa", "sg", "in", "ru"]

# 国内成功响应的data数据
class SuccessAccessTokenDataCN(TypedDict):
    accessToken: str
    expireTime: int

# 海外成功响应的data数据
class SuccessAccessTokenDataEN(TypedDict):
    accessToken: str
    expireTime: int
    areaDomain: str

# 成功响应的data数据（国内/海外统一Union类型）
SuccessAccessTokenData = Union[SuccessAccessTokenDataCN, SuccessAccessTokenDataEN]

# 成功和错误码定义
SuccessCode = Literal["200"]
ErrorCode = Literal["10001", "10005", "10017", "10030", "49999"]

# 国内成功响应
class SuccessResponseCN(TypedDict):
    code: SuccessCode
    msg: str
    data: SuccessAccessTokenData

# 海外成功响应
class SuccessResponseEN(TypedDict):
    code: SuccessCode
    msg: str
    data: SuccessAccessTokenData

SuccessResponse = Union[SuccessResponseCN, SuccessResponseEN]

# 国内错误响应的data数据（data: null）
class ErrorAccessTokenDataCN(TypedDict):
    pass  # 表示 data 为 null（通过ErrorResponseCN中的data: None来明确）

# 海外错误响应的data数据（无data字段）
class ErrorAccessTokenDataEN(TypedDict):
    pass  # 表示无data字段

# 错误响应的data数据（国内/海外统一）
ErrorAccessTokenData = Union[ErrorAccessTokenDataCN, ErrorAccessTokenDataEN]

# 国内错误响应
class ErrorResponseCN(TypedDict):
    code: ErrorCode
    msg: str
    data: None  # 明确表示 data 为 null

# 海外错误响应
class ErrorResponseEN(TypedDict):
    code: ErrorCode
    msg: str
    # 没有 data 字段

# 统一错误响应类型
ErrorResponse = Union[ErrorResponseCN, ErrorResponseEN]

# 统一响应类型（成功或失败）
Response = Union[SuccessResponse, ErrorResponse]

# 在类型定义部分，添加：
AccessTokenDataRaw = Union[SuccessAccessTokenData, ErrorAccessTokenData]

# 3. 辅助类 (Helper Class)
class AccessTokenData:
    """
    封装从萤石API返回的data字段，支持点号访问。
    所有属性均为只读，由API响应数据初始化。

    Attributes:
        access_token (str | None): 访问令牌。
        expire_time (int | None): 过期时间戳（毫秒）。
        area_domain (str | None): 海外区域域名，仅海外接口返回，国内为 None。
    """
    def __init__(self, data: AccessTokenDataRaw):
        self.access_token = data.get("accessToken")
        self.expire_time = data.get("expireTime")
        self.area_domain = data.get("areaDomain")  # 仅海外区域存在

    def __repr__(self):
        return f"<AccessTokenData access_token='{self.access_token}' expire_time={self.expire_time} area_domain='{self.area_domain}'>"

# 4. 主类 (Main Class)
class AccessToken:
    """
    获取萤石开放平台 accessToken 的类。
    实例化即自动请求，响应数据作为属性暴露。
    使用方式：
        response = AccessToken(app_key, app_secret, region='us')
        print(response.code)
        print(response.data.access_token)
        print(response.data.area_domain)
    """

    def __init__(self, app_key: str, app_secret: str, region: Region = "cn"):
        self.app_key = app_key
        self.app_secret = app_secret
        self.region = region

        # 立即请求 token
        result: Response = self._request_access_token()

        # 将响应结构映射为实例属性
        self.code = result.get("code", "未知")
        self.msg = result.get("msg", "无消息")

        # 如果请求失败（code 非200），抛出异常
        if self.code != "200":
            error_remark = ERROR_CODE_REMARKS.get(self.code, "未知错误")
            raise EZVIZAuthError(code=self.code, message=self.msg, remark=error_remark)

        # 此时一定是成功响应，封装 data 为对象
        success_result = cast(SuccessResponse, result)
        raw_data = success_result["data"]
        # 根据区域类型进行更精确的类型转换
        if self.region == "cn":
            raw_data = cast(SuccessAccessTokenDataCN, raw_data)
        else:
            raw_data = cast(SuccessAccessTokenDataEN, raw_data)
        self.data = AccessTokenData(raw_data)

    def _get_url(self) -> str:
        """根据 region 确定请求 URL"""
        url_map = {
            "cn": "https://open.ys7.com/api/lapp/token/get",
            "en": "https://open.ezvizlife.com/api/lapp/token/get",
            "eu": "https://ieuopen.ezvizlife.com/api/lapp/token/get",
            "us": "https://iusopen.ezvizlife.com/api/lapp/token/get",
            "sa": "https://isaopen.ezvizlife.com/api/lapp/token/get",
            "sg": "https://isgpopen.ezvizlife.com/api/lapp/token/get",
            "in": "https://iindiaopen.ezvizlife.com/api/lapp/token/get",
            "ru": "https://irusopen.ezvizlife.com/api/lapp/token/get"
        }
        if self.region not in url_map:
            raise ValueError(f"无效的区域标识符: {self.region}")
        return url_map[self.region]

    def _request_access_token(self) -> Response:
        """执行 HTTP 请求并返回原始 JSON 响应"""
        url = self._get_url()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {"appKey": self.app_key, "appSecret": self.app_secret}

        response = requests.post(url, headers=headers, data=payload)
        
        response.raise_for_status()
        result = response.json()
        # 由于 requests 返回的是 Any，我们需要显式告诉类型检查器：这就是 Response
        return cast(Response, result)

    def __repr__(self):
        return f"<AccessToken code={self.code} msg='{self.msg}' data={self.data}>"

# 5. 公共函数 (Public Function)
def get_access_token(
    app_key: str,
    app_secret: str,
    region: Region = "cn"
) -> AccessToken:  # ← 返回 AccessToken，不是 Response
    """
    获取萤石开放平台访问令牌。

    返回一个 AccessToken 对象，包含结构化数据和状态信息。
    推荐用于所有生产环境代码。

    Raises:
        EZVIZAuthError: 认证失败时抛出。
        ValueError: 区域参数无效。
        requests.RequestException: 网络错误。
    """
    return AccessToken(app_key, app_secret, region)
