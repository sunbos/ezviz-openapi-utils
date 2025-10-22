#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EZVIZ OpenAPI Utils Package

This package provides a comprehensive Python library for interacting with the EZVIZ
OpenAPI platform. It offers simplified authentication, token management, and
access to approximately 143 API methods for device management, control, and monitoring.

Main Components:
- Client: EZVIZ API client with automatic token management
- AccessToken: OAuth access token object
- get_access_token: Authentication function for obtaining access tokens
- EZVIZOpenAPI: Comprehensive collection of EZVIZ OpenAPI methods

Author: SunBo <1443584939@qq.com>
License: MIT
Version: 0.1.0
"""

__version__ = '0.1.0'
__author__ = 'SunBo'
__email__ = '1443584939@qq.com'
__license__ = 'MIT'

# 导入核心模块
from .client import Client
from .oauth import get_access_token, AccessToken
from .api import EZVIZOpenAPI

# 定义公开接口
__all__ = [
    'Client',
    'get_access_token',
    'AccessToken',
    'EZVIZOpenAPI'
]