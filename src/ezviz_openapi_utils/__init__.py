"""
ezviz_openapi_utils 包提供与萤石开放平台交互的核心工具类和函数。
主要功能包括：
- Client: 萤石API客户端
- AccessToken: 访问令牌对象
- get_access_token: 获取访问令牌的认证函数
- EZVIZOpenAPI: 萤石开放平台API接口集合
"""

__version__ = '0.1.0'

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