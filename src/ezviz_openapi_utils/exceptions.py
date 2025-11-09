#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EZVIZ OpenAPI Exceptions Module

This module defines the exception hierarchy for the EZVIZ OpenAPI platform.
It provides specific exception classes for different types of errors including
authentication failures, API errors, and device-specific errors.

Author: SunBo <1443584939@qq.com>
License: MIT
"""

class EZVIZBaseError(Exception):
    """萤石开放平台基础异常类"""
    def __init__(self, code: str, message: str, remark: str = ""):
        self.code = code
        self.message = message
        self.remark = remark
        super().__init__(f"Code {code}: {message} - {remark}")

class EZVIZAuthError(EZVIZBaseError):
    """萤石开放平台认证相关异常"""
    pass

class EZVIZAPIError(EZVIZBaseError):
    """萤石开放平台API调用异常"""
    pass

class EZVIZDeviceNotSupportedError(EZVIZBaseError):
    """设备不支持该功能的异常"""
    def __init__(self, code: str, message: str, device_serial: str = "", api_name: str = ""):
        self.device_serial = device_serial
        self.api_name = api_name
        remark = f"设备 {device_serial} 不支持功能 {api_name}: {message}"
        super().__init__(code, message, remark)
