#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EZVIZ OpenAPI Module

This module provides the EZVIZOpenAPI class which serves as a comprehensive interface
to the EZVIZ OpenAPI platform. It includes approximately 143 API methods covering
device management, PTZ control, intelligent features, security settings, firmware
updates, and more.

Author: SunBo <1443584939@qq.com>
License: MIT
"""

import time
import requests
from typing import Any, Dict, Literal, Optional, Union
from .client import Client
from .exceptions import EZVIZAPIError, EZVIZDeviceNotSupportedError

GLOBAL_ERROR_CODE_MAP = {
    "2001": "摄像机未注册到萤石云平台，请仔细检查摄像机的网络配置，确保连接到网络",
    "2003": "参考服务中心排查方法",
    "2030": "请确认该设备是否能支持接入萤石云，如有疑问可联系客服热线4007005998确认",
    "7007": "分享和删除分享必须全部由接口形式操作，如果与萤石客户端混用会造成这个问题，解决办法：在萤石客户端清空所有相关分享数据并重新添加设备，再通过接口操作即可",
    "9049": "个人版套餐只有1M带宽",
    "10001": "参数为空或者格式不对",
    "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
    "10005": "确认appKey状态，不通过或者冻结状态会返回该错误码",
    "10007": "根据用户类型调用次数有所不同，个人版用户可通过升级企业版的方式提高接口调用次数限制",
    "10008": "①获取签名方式详见apidemo及[旧]API文档 ②注意编码格式为UTF-8",
    "10010": "请调用同步服务器时间接口进行校时",
    "10011": "参照绑定流程",
    "10014": "获取AccessToken时所用appKey与SDK所用appKey不一致",
    "10017": "请填写在官网申请的应用秘钥",
    "10018": "请检查获取accessToken对应的appKey和SDK中设置的appKey是否一致",
    "10023": "请填写在官网填写的应用包名-->(详细信息)-->(应用类型:移动应用)-->应用包名(IOS为bundleId)",
    "10026": "个人版免费用户设备接入数限制，升级企业版可取消限制",
    "10027": "服务使用的个人版appKey数量超出安全限制，升级企业版可取消限制",
    "10028": "个人版用户抓图接口日调用次数超出限制",
    "10030": "请检查appKey和appSecret是否对应",
    "20001": "请检查摄像头设备是否重新添加过、通道参数是否更新",
    "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
    "20005": "已去掉安全验证",
    "20007": "参考服务中心排查方法",
    "20008": "设备响应超时，请检测设备网络或重试",
    "20010": "验证码在设备标签上，六位大写字母，注意大小写",
    "20018": "确认设备是否属于用户",
    "20025": "确认设备是否由添加过该设备且申请过分享的账户下是否还存在分享记录",
    "20031": "请在萤石客户端关闭终端绑定，参考此步骤",
    "60020": "请确认设备是否支持该命令",
    "60057": "检查IPC与NVR是否有关联关系",
    "60060": "请前往官网设置直播",
    "60083": "设备正在操作隐私遮蔽，无法进行当前操作",
    "60084": "设备正在操作隐私遮蔽，无法进行当前操作",
    "60085": "设备确权接口",
    "60086": "设备确权接口"
}

# 设备不支持的错误码列表
DEVICE_NOT_SUPPORTED_CODES = {
    "2030", "20015", "20019", "60000", "60020", "60047", "60050", "60051", "60053"
}


class EZVIZOpenAPI:
    """
    萤石开放平台API接口集合。
    所有具体的API方法都应定义在此类中。
    """
    def __init__(self, client: Client):
        """
        初始化API类。
        Args:
            client (Client): 已经初始化的Client实例。
        """
        self._client = client

        # 核心逻辑：根据区域和 area_domain 确定基础URL
        if client.area_domain:
            # 海外区域：直接使用从令牌接口获取的精确区域域名
            self._base_url = client.area_domain
        else:
            # 国内区域 (cn)：area_domain 为 None，使用固定域名
            self._base_url = "https://open.ys7.com"

    def _handle_api_response(
        self,
        http_response: requests.Response,
        api_name: str = "",
        device_serial: str = "",
        error_code_map: Optional[Dict[str, str]] = None,
        response_format: str = "default"  # "default", "meta", "result", "code"
    ) -> Dict[str, Any]:
        """
        统一的API响应处理方法

        Args:
            http_response: HTTP响应对象
            api_name: API方法名，用于错误提示
            device_serial: 设备序列号，用于错误提示
            error_code_map: 自定义错误码映射表
            response_format: 响应格式类型
                - "default": 标准格式，检查根级别的 code 字段
                - "meta": 检查 meta.code 字段
                - "result": 检查 result.code 字段
                - "code": 直接检查 code 字段（字符串类型）

        Returns:
            Dict[str, Any]: 解析后的响应数据

        Raises:
            EZVIZAPIError: 当API调用失败且非设备不支持时抛出
        """
        # 先获取响应数据，不管HTTP状态码（目的是先判断设备是否支持相关功能）
        try:
            response_data = http_response.json()
        except ValueError:
            # 如果JSON解析失败，检查HTTP状态
            http_response.raise_for_status()
            raise EZVIZAPIError("HTTP_ERROR", f"HTTP {http_response.status_code}", "无法解析响应数据")

        # 根据格式获取错误码和消息
        code, message = self._extract_code_and_message(response_data, response_format)

        # 检查是否是设备不支持的错误
        if str(code) in DEVICE_NOT_SUPPORTED_CODES:
            not_supported_error = EZVIZDeviceNotSupportedError(
                str(code),
                message,
                device_serial,
                api_name
            )
            raise not_supported_error

        # 检查HTTP状态码（如果不是设备不支持的情况）
        try:
            http_response.raise_for_status()
        except requests.HTTPError as e:
            raise EZVIZAPIError("HTTP_ERROR", str(e), f"HTTP请求失败: {e}")

        # 检查业务错误码
        if code not in (200, "200"):
            # 使用自定义错误映射或默认映射
            error_description = self._get_error_description(str(code), error_code_map)
            raise EZVIZAPIError(str(code), message, error_description)

        return response_data

    def _extract_code_and_message(self, response_data: Dict[str, Any], response_format: str) -> tuple:
        """从响应数据中提取错误码和消息"""
        if response_format == "meta":
            meta = response_data.get('meta', {})
            return meta.get('code'), meta.get('message', '未知错误')
        elif response_format == "result":
            result = response_data.get('result', {})
            return result.get('code'), result.get('msg', '未知错误')
        elif response_format == "code":
            return response_data.get('code'), response_data.get('msg', '未知错误')
        else:  # default
            # 默认格式，优先检查 code，然后检查 meta.code
            code = response_data.get('code')
            message = response_data.get('msg', response_data.get('message', '未知错误'))
            if code is None:
                meta = response_data.get('meta', {})
                code = meta.get('code')
                message = meta.get('message', message)
            return code, message

    def _get_error_description(self, code: str, custom_map: Optional[Dict[str, str]] = None) -> str:
        """获取错误描述"""
        if custom_map and code in custom_map:
            return custom_map[code]
        return GLOBAL_ERROR_CODE_MAP.get(code, "未知错误")

    def is_device_support_ezviz(
        self,
        model: str,
        version: str,
        app_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询设备是否支持萤石协议。
        参考文档: 查询设备是否支持萤石协议

        Args:
            model (str): 设备型号（必填）
            version (str): 设备版本号（必填）
            app_key (str, optional): 应用密钥，默认使用客户端初始化的app_key（非必填自动处理，官方必填）

        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'data', 'code', 'msg' 字段。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'is_device_support_ezviz' 仅限 'cn' 区域使用。", "区域限制错误")

        if app_key is None:
            app_key = self._client.app_key

        url = f"{self._base_url}/api/lapp/device/support/ezviz"
        payload = {
            'accessToken': self._client.access_token,
            'appKey': app_key,
            'model': model,
            'version': version
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或参数不存在",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="is_device_support_ezviz",
            device_serial="",
            response_format="code",
            error_code_map=error_description_dict
        )

    def search_device_info(
        self,
        device_serial: str,
        model: Optional[str] = None,
        method: Literal['GET', 'POST'] = 'POST'
    ) -> Dict[str, Any]:
        """
        查询设备信息。
        参考文档: 查询设备信息

        Args:
            device_serial (str): 设备序列号（必填）
            model (str, optional): 设备型号（非必填）
            method (str, optional): HTTP 请求方法，仅支持 'GET' 或 'POST'。默认为 'POST'。

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
            ValueError: 当 method 参数不是 'GET' 或 'POST' 时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'search_device_info' 仅限 'cn' 区域使用。", "区域限制错误")

        # 虽然类型提示已限制，但运行时仍可传入非法值（如通过 eval），做双重保险
        if method not in ('GET', 'POST'):
            raise ValueError(f"不支持的HTTP方法: {method}。仅支持 'GET' 或 'POST'。")

        url = f"{self._base_url}/api/v3/device/searchDeviceInfo"

        # 根据方法准备参数
        kwargs = {}
        if method == 'GET':
            kwargs['params'] = {
                'accessToken': self._client.access_token,
                'deviceSerial': device_serial
            }
            if model is not None:
                kwargs['params']['model'] = model
        else:  # POST
            kwargs['data'] = {
                'accessToken': self._client.access_token,
                'deviceSerial': device_serial
            }
            if model is not None:
                kwargs['data']['model'] = model

        http_response = self._client._session.request(method, url, **kwargs, headers={'Content-Type': "application/x-www-form-urlencoded"})

        # 自定义响应处理逻辑，专门处理search_device_info的成功状态码
        try:
            response_data = http_response.json()
        except ValueError:
            # 如果JSON解析失败，检查HTTP状态
            http_response.raise_for_status()
            raise EZVIZAPIError("HTTP_ERROR", f"HTTP {http_response.status_code}", "无法解析响应数据")

        # 检查HTTP状态码
        try:
            http_response.raise_for_status()
        except requests.HTTPError as e:
            raise EZVIZAPIError("HTTP_ERROR", str(e), f"HTTP请求失败: {e}")

        # 从result字段提取code和msg
        result = response_data.get('result', {})
        code = result.get('code')
        message = result.get('msg', '未知错误')

        # 检查是否是设备不支持的错误
        if str(code) in DEVICE_NOT_SUPPORTED_CODES:
            not_supported_error = EZVIZDeviceNotSupportedError(
                str(code),
                message,
                device_serial,
                "search_device_info"
            )
            raise not_supported_error

        # search_device_info API的特殊成功状态码
        SEARCH_DEVICE_SUCCESS_CODES = {"200", "20020", "20023", "20029"}

        if str(code) not in SEARCH_DEVICE_SUCCESS_CODES:
            # 处理其他错误码
            error_description_dict = {
                "10001": "请求参数错误",
                "10002": "accessToken过期或异常",
                "10004": "accessToken不合法",
                "20002": "用户不存在",
                "20013": "设备已被别人添加",
                "20014": "设备序列不正确",
                "60107": "不支持错误",
                "49999": "系统错误"
            }
            error_description = error_description_dict.get(str(code), "未知错误")
            raise EZVIZAPIError(str(code), message, error_description)

        return response_data
    
    def add_device(
        self,
        device_serial: str,
        validate_code: str,
    ) -> Dict[str, Any]:
        """
        添加设备。
        参考文档: 添加设备

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            validate_code (str): 设备验证码，设备机身上的六位大写字母（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/add"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'validateCode': validate_code
        }
        http_response = self._client._session.request('POST', url, data=payload,
                                                    headers={'Content-Type': 'application/x-www-form-urlencoded'})
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "请重新获取 accessToken",
            "10005": "appKey 被冻结，请检查您的应用状态",
            "20002": "设备未注册至萤石云，请先激活设备",
            "20007": "检查设备是否在线，网络连接是否正常",
            "20010": "检查设备验证码是否输入错误",
            "20011": "检查设备网络等是否正常，或稍后重试",
            "20013": "该设备已被其他账号添加，请先解绑",
            "20017": "设备已经添加到当前账号下，无需重复添加",
            "49999": "接口调用异常，建议稍后重试或联系技术支持",
            "60066": "本地更新验证码：\n    https://statics.ys7.com/device/image/servicepic/16.png",
            "60058": "设备需要确权：\n    1. 设备确权接口文档：https://open.ys7.com/help/664\n    2. 确权快速操作指南：https://open.ys7.com/bbs/article/106",
            "60034": "此设备不支持直连云服务，请将设备先关联到海康威视硬盘录像机",
            "60085": "设备确权问题：\n    请参考接口文档：https://open.ys7.com/help/664",
            "60086": "设备确权问题：\n    请参考接口文档：https://open.ys7.com/help/664"
        }
        return self._handle_api_response(
            http_response,
            api_name="add_device",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )
    
    def delete_device(
        self,
        device_serial: str,
    ) -> Dict[str, Any]:
        """
        删除设备。
        参考文档: 删除设备

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/delete"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "请重新获取 accessToken",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "20031": "请在萤石客户端关闭终端绑定，参考此步骤：https://service.ezviz.com/questions/answer?id=14098",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="delete_device",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def device_wifi_qrcode(
        self,
        ssid: str,
        password: str
    ) -> Dict[str, Any]:
        """
        生成设备WiFi二维码。
        参考文档: 生成设备WiFi二维码

        Args:
            ssid (str): 路由器SSID，即WIFI名称，建议不要设置中文名称（必填）
            password (str): WIFI密码（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'device_wifi_qrcode' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/lapp/device/wifi/qrcode"
        payload = {
            'accessToken': self._client.access_token,
            'ssid': ssid,
            'password': password
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "请重新获取 accessToken",
            "10005": "appKey被冻结",
            "10017": "确认appKey是否正确",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="device_wifi_qrcode",
            device_serial="",
            response_format="code",
            error_code_map=error_description_dict
        )
        
    def device_permission_check(
        self,
        device_serial: str,
        ssid: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        自动确权接口：验证设备权限并返回设备在线状态。
        参考文档: 自动确权接口

        Args:
            device_serial (str): 设备序列号（必填）
            ssid (str, optional): APP当前连接的SSID（非必填）
            client_ip (str, optional): 客户端互联网IP地址（非必填）

        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 和 'status' 字段。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/userdevice/v3/devices/op/permission"
        params = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        
        if ssid is not None:
            params['ssid'] = ssid
        if client_ip is not None:
            params['clientIP'] = client_ip

        http_response = self._client._session.request('GET', url, params=params)

        # 错误码映射表
        error_description_dict = {
            "401": "Unauthorized",
            "403": "Forbidden",
            "404": "Not Found",
            "504": "网络异常",
            "2009": "超时",
            "2021": "确权失败",
            "70000": "确权失败"
        }
        return self._handle_api_response(
            http_response,
            api_name="device_permission_check",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def get_device_realtime_status(
        self,
        device_serial: str,
    ) -> Dict[str, Any]:
        """
        获取设备实时状态（在线/离线）。
        参考文档: 离线确认接口

        Args:
            device_serial (str): 设备序列号（必填）

        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 和 'status' 字段。
                            status 为 0 表示离线，1 表示在线。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_realtime_status' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/userdevice/v3/devices/realtimestatus"
        params = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
        }

        http_response = self._client._session.request('GET', url, params=params)

        # 错误码映射表
        error_description_dict = {
            "401": "Unauthorized",
            "403": "Forbidden",
            "404": "Not Found",
            "504": "网络异常",
            "2009": "超时",
            "2021": "确权失败"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_realtime_status",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def get_device_permissions(
        self,
        device_serial: str,
    ) -> Dict[str, Any]:
        """
        获取设备权限信息。
        参考文档: 在线确权接口

        Args:
            device_serial (str): 设备序列号（必填）

        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 和 'permissions' 字段。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_permissions' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/userdevice/v3/devices/permission"
        params = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
        }

        http_response = self._client._session.request('GET', url, params=params)

        # 错误码映射表
        error_description_dict = {
            "401": "Unauthorized",
            "403": "Forbidden",
            "404": "Not Found",
            "504": "网络异常",
            "2009": "超时",
            "2021": "确权失败",
            "70000": "确权失败"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_permissions",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def update_device_name(
        self,
        device_serial: str,
        device_name: str
    ) -> Dict[str, Any]:
        """
        修改云端设备名称。
        参考文档: 修改云端设备名称

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            device_name (str): 设备名称，长度不大于50字节，不能包含特殊字符（必填）

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/name/update"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'deviceName': device_name
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="update_device_name",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def update_camera_name(
        self,
        device_serial: str,
        name: str,
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        修改云端通道名称。
        参考文档: 修改云端通道名称

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            name (str): 通道名称，长度不大于50字节，不能包含特殊字符（必填）
            channel_no (Optional[int]): 非必选参数，不为空表示修改指定通道名称，为空表示修改通道1名称（可选）

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'update_device_name' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/lapp/camera/name/update"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'name': name
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
            
        http_response = self._client._session.request('POST', url, data=payload)

        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "20032": "检查设备对应通道是否存在",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="update_camera_name",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )
    
    def add_ipc_device(
        self,
        device_serial: str,
        ipc_serial: str,
        channel_no: Optional[int] = None,
        validate_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        NVR设备关联IPC。
        参考文档: NVR设备关联IPC

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            ipc_serial (str): 待关联的IPC设备序列号（必填）
            channel_no (Optional[int]): 非必选参数，不为空表示给指定通道关联IPC，为空表示给通道1关联IPC（可选）
            validate_code (Optional[str]): 非必选参数，IPC设备验证码，默认为空（可选）

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/ipc/add"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'ipcSerial': ipc_serial
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
        if validate_code is not None:
            payload['validateCode'] = validate_code
        http_response = self._client._session.request('POST', url, data=payload)

        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60012": "设备返回其他错误码",
            "60020": "确认设备是否支持关联IPC",
            "60055": "检查IPC设备码流"
        }
        return self._handle_api_response(
            http_response,
            api_name="add_ipc_device",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def delete_ipc_device(
        self,
        device_serial: str,
        ipc_serial: str,
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        NVR设备删除关联IPC。
        参考文档: NVR设备删除关联IPC

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            ipc_serial (str): 待关联的IPC设备序列号（必填）
            channel_no (Optional[int]): 非必选参数，不为空表示给指定通道关联IPC，为空表示给通道1关联IPC（可选）

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/ipc/delete"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'ipcSerial': ipc_serial
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60012": "设备返回其他错误码",
            "60020": "确认设备是否支持关联IPC"
        }
        return self._handle_api_response(
            http_response,
            api_name="delete_ipc_device",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def nvr_device_camera_limit(
        self,
        device_serial: str,
        channel_no: str,
        enable: int
    ) -> Dict[str, Any]:
        """
        显示或者隐藏NVR下的通道。
        参考文档: NVR设备隐藏IPC API文档
        
        注意：此API需要将accessToken放在Header中，而不是请求参数中。

        Args:
            device_serial (str): 设备序列号（必填）
            channel_no (str): 通道号（必填）
            enable (int): 通道状态：1-显示，0-隐藏（必填）

        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'code', 'msg' 字段。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'nvr_device_camera_limit' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/open/device/camera/limit"
        payload = {
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'enable': enable
        }
        
        http_response = self._client._session.request('POST', url, data=payload, headers={'accessToken': self._client.access_token})

        error_description_dict = {
            "10001": "参数错误",
            "10002": "accessToken过期或异常",
            "10031": "子账户或萤石用户没有权限",
            "20015": "设备不支持该功能",
            "20018": "该用户不拥有该设备"
        }
        return self._handle_api_response(
            http_response,
            api_name="nvr_device_camera_limit",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_gb_license_list(
        self,
        product_key: str,
        page_index: Optional[int] = 0,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        获取国标License列表。
        参考文档: 获取国标License列表

        Args:
            product_key (str): 项目编码（必填）
            page_index (int, optional): 起始页，默认0（非必填）
            page_size (int, optional): 分页大小，默认10，最大50（非必填）

        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 和 'data' 字段。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_gb_license_list' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/v3/device/register/gb/license/list"
        payload = {
            'accessToken': self._client.access_token,
            'productKey': product_key,
            'pageIndex': page_index,
            'pageSize': page_size
        }

        http_response = self._client._session.request('POST', url, data=payload)

        return self._handle_api_response(
            http_response,
            api_name="get_gb_license_list",
            device_serial="",
            response_format="meta"
        )
    
    def get_device_info(
        self,
        device_serial: str,
    ) -> Dict[str, Any]:
        """
        查询用户下指定设备的基本信息。
        参考文档: 获取单个设备信息

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）

        Returns:
            Dict[str, Any]: API返回的原始数据

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/info"

        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }

        http_response = self._client._session.request('POST', url, data=payload)

        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_info",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )
    
    def list_devices_by_page(
        self,
        page_start: Optional[int] = 0,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        分页查询设备列表（根据页码）。
        参考文档: 分页查询设备列表
        Args:
            page_start (int, optional): 分页页码，起始页从0开始，不超过400页。默认为0。
            page_size (int, optional): 分页大小，默认为10，不超过50。
        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'data', 'code', 'msg', 'page' 字段。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/list"
        payload = {
            'accessToken': self._client.access_token,
            'pageStart': page_start,
            'pageSize': page_size
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }

        return self._handle_api_response(
            http_response,
            api_name="list_devices_by_page",
            response_format="code",
            error_code_map=error_description_dict
        )

    def list_devices_by_id(
        self,
        start_id: str,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        根据设备索引ID分页查询设备列表。
        参考文档: 根据设备索引id分页查询设备列表
        Args:
            start_id (str): 起始条目索引，首页传"0"。
            page_size (int, optional): 分页大小，默认为10，不超过50。
        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'data', 'code', 'msg', 'page' 字段。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/list"
        payload = {
            'accessToken': self._client.access_token,
            'id': start_id,
            'pageSize': page_size
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "无效参数",
            "10002": "accessToken过期或异常",
            "10004": "需要使用B账号",
            "10005": "appKey异常",
            "49999": "数据异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="list_devices_by_id",
            device_serial="",
            response_format="code",
            error_code_map=error_description_dict
        ) 

    def get_camera_list(
        self,
        page_start: Optional[int] = 0,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        获取视频通道列表。
        参考文档: 获取监控点列表

        Args:
            page_start (int, optional): 分页起始页，从0开始。默认为 0。
            page_size (int, optional): 分页大小，默认为10，最大为50。默认为 10。

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/camera/list"
        payload = {
            'accessToken': self._client.access_token,
            'pageStart': page_start,
            'pageSize': page_size
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数错误",
            "10002": "accessToken异常或过期",
            "10005": "appKey异常",
            "20002": "设备不存在",
            "20014": "deviceSerial不合法",
            "20018": "该用户不拥有该设备",
            "49999": "数据异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_camera_list",
            device_serial="",
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_device_camera_list(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取指定设备的通道信息。
        参考文档: 获取指定设备的通道信息

        Args:
            device_serial (str): 设备序列号（字母需为大写）。

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/camera/list"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数错误",
            "10002": "accessToken异常或过期",
            "10005": "appKey异常",
            "20002": "设备不存在",
            "20014": "deviceSerial不合法",
            "20018": "该用户不拥有该设备",
            "49999": "数据异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_camera_list",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_device_status(
        self,
        device_serial: str,
        channel_no: Optional[int] = 1
    ) -> Dict[str, Any]:
        """
        该接口用于根据序列号通道号获取设备状态信息。
        参考文档: 获取设备状态信息

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int, optional): 通道号，默认为1（非必填）

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/status/get"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )
    
    def get_device_channel_status(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备通道状态。
        参考文档: 获取NVR通道状态信息

        Returns:
            Dict[str, Any]: API返回的原始数据。

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_channel_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/open/device/metadata/channel/status"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }

        http_response = self._client._session.request('GET', url, headers=headers)
        error_description_dict = {
            "10001": "参数错误",
            "10002": "accessToken过期或异常",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_channel_status",
            device_serial=device_serial,
            response_format="result",
            error_code_map=error_description_dict
        )

    def get_device_connection_info(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询用户下指定设备的网络连接信息。
        参考文档: 获取单个设备连接信息

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。

        Returns:
            Dict[str, Any]: 设备连接信息
        """


        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_connection_info' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/lapp/device/connection/info"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10004": "需要使用B账号",
            "10005": "appKey被冻结",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_connection_info",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def create_device_add_token_url(
        self,
        expire_time: int,
        note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建用于B端客户添加设备的授权连接。
        适用范围：B端设备添加工具
        账号类型：仅支持开发者账号使用
        参考文档: 创建授权连接
        Args:
            expire_time (int): 过期时间，单位为小时，取值范围【1~720】。（必填）
            note (str, optional): 备注信息。（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 和 'data' 字段。
                            'data' 中包含 'id', 'expireTime', 'url', 'note', 'expired'。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'create_device_add_token_url' 仅限 'cn' 区域使用。", "区域限制错误")
        
        url = f"{self._base_url}/api/service/device/add/tokenUrl"
        payload = {
            'expireTime': expire_time
        }
        if note is not None:
            payload['note'] = note
            
        headers = {
            'Content-Type': 'application/json',
            'accessToken': self._client.access_token
        }

        http_response = self._client._session.request('POST', url, json=payload, headers=headers)

        error_description_dict = {
            "403": "无权限，请确认accessToken是否为开发者账号"
        }
        return self._handle_api_response(
            http_response,
            api_name="create_device_add_token_url",
            device_serial="",
            response_format="meta",
            error_code_map=error_description_dict
        )

    def get_device_add_note_info(
        self,
        device_serial: Optional[str] = None,
        id: Optional[int] = None,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        查询通过B端添加工具添加的设备信息，包含设备序列号、绑定方式、绑定时间、授权连接的备注。
        可以通过设备序列号精确查询，或通过分页查询。
        适用范围：B端设备添加工具
        账号类型：仅支持开发者账号使用
        参考文档: 设备备注信息查询
        Args:
            device_serial (str, optional): 设备序列号，用于查询该设备的详细信息。如果提供，则忽略分页参数。（非必填）
            id (int, optional): 起始页索引，默认为None（即从第一页开始），查询结果不包含该数据。（非必填）
            page_size (int, optional): 分页大小，默认为10，取值范围【1~50】。（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 和 'data' 字段。
                            'data' 是一个列表，每个元素包含 'id', 'deviceSerial', 'note', 'bindTime', 'bindType'。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_add_note_info' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/service/device/add/tokenNote"
        params = {}
        headers = {
            'accessToken': self._client.access_token
        }

        if device_serial is not None:
            # 如果提供了设备序列号，则在Header中传递
            headers['deviceSerial'] = device_serial

        if id is not None:
            params['id'] = id
        if page_size is not None:
            params['pageSize'] = page_size

        http_response = self._client._session.request('GET', url, params=params, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_add_note_info",
            device_serial=device_serial or "",
            response_format="meta"
        )

    def list_device_add_token_urls(
        self,
        id: Optional[str] = None,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        查询开发者账号下所有的授权添加连接信息。
        适用范围：B端设备添加工具
        账号类型：仅支持开发者账号使用
        参考文档: 开发者授权列表查询
        Args:
            id (str, optional): 起始页索引，默认为None（即从第一页开始），查询结果不包含该数据。（非必填）
            page_size (int, optional): 分页大小，默认为10，取值范围【1~50】。（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 和 'data' 字段。
                            'data' 是一个列表，每个元素包含 'id', 'expireTime', 'url', 'note', 'expired'。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'list_device_add_token_urls' 仅限 'cn' 区域使用。", "区域限制错误")
        
        url = f"{self._base_url}/api/service/device/add/tokenUrls"
        params = {}
        headers = {
            'accessToken': self._client.access_token
        }
        if id is not None:
            params['id'] = id
        if page_size is not None:
            params['pageSize'] = page_size

        http_response = self._client._session.request('GET', url, params=params, headers=headers)

        error_description_dict = {
            "403": "无权限，请确认accessToken是否为开发者账号"
        }
        return self._handle_api_response(
            http_response,
            api_name="list_device_add_token_urls",
            device_serial="",
            response_format="meta",
            error_code_map=error_description_dict
        )

    def get_device_capacity(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        该接口用户根据设备序列号查询设备能力集
        参考文档: 获取设备能力集
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """

        url = f"{self._base_url}/api/lapp/device/capacity"
        
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }

        http_response = self._client._session.request('POST', url, data=payload)

        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "20002": "设备序列号输入有误或者设备未添加或者通道异常",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_capacity",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def start_ptz_control(
        self,
        device_serial: str,
        channel_no: int,
        direction: int,
        speed: int
    ) -> Dict[str, Any]:
        """
        启动云台控制
        参考文档: 启动云台控制
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
            direction (int): 操作命令：0-上，1-下，2-左，3-右，4-左上，5-左下，6-右上，7-右下，8-物理放大，9-物理缩小，10-调整近焦距，11-调整远焦距，16-自动控制（必填）
            speed (int): 云台速度：0-慢，1-适中，2-快，海康设备参数不可为0（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/ptz/start"

        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'direction': direction,
            'speed': speed
        }

        http_response = self._client._session.request('POST', url, data=payload)

        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60000": "设备不支持云台控制",
            "60006": "稍候再试",
            "60020": "确认设备是否支持该操作"
        }
        return self._handle_api_response(
            http_response,
            api_name="start_ptz_control",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def stop_ptz_control(
        self,
        device_serial: str,
        channel_no: int,
        direction: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        停止云台控制
        参考文档: 停止云台控制
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
            direction (Optional[int]): 操作命令：0-上，1-下，2-左，3-右，4-左上，5-左下，6-右上，7-右下，8-物理放大，9-物理缩小，10-调整近焦距，11-调整远焦距，16-自动控制（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/ptz/stop"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        if direction is not None:
            payload['direction'] = direction
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60000": "设备不支持云台控制",
            "60006": "稍候再试",
            "60020": "确认设备是否支持该操作"
        }
        return self._handle_api_response(
            http_response,
            api_name="stop_ptz_control",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def device_mirror_ptz(
        self,
        device_serial: str,
        channel_no: int,
        command: int
    ) -> Dict[str, Any]:
        """
        对设备进行镜像翻转操作(需要设备支持)。
        参考文档: 镜像翻转
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
            command (int): 镜像方向：0-上下, 1-左右, 2-中心（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/ptz/mirror"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'command': command
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60006": "稍候再试",
            "60020": "确认设备是否支持该操作"
        }
        return self._handle_api_response(
            http_response,
            api_name="device_mirror_ptz",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def add_device_preset(
        self,
        device_serial: str,
        channel_no: int
    ) -> Dict[str, Any]:
        """
        支持云台控制操作的设备添加预置点，该接口需要设备支持能力集：ptz_preset=1
        参考文档: 添加预置点
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/preset/add"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60006": "稍候再试",
            "60008": "C6预置点最大限制个数为12"
        }
        return self._handle_api_response(
            http_response,
            api_name="add_device_preset",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def move_device_preset(
        self,
        device_serial: str,
        channel_no: int,
        index: int
    ) -> Dict[str, Any]:
        """
        移动设备预置点。
        参考文档: 移动预置点
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
            index (int): 预置点，C6设备预置点是1-12（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/preset/move"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'presetIndex': index
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60006": "稍候再试",
            "60020": "确认设备是否支持该操作"
        }
        return self._handle_api_response(
            http_response,
            api_name="move_device_preset",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def clear_device_preset(
        self,
        device_serial: str,
        channel_no: int,
        index: int
    ) -> Dict[str, Any]:
        """
        清除预置点。
        参考文档: 清除预置点
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
            index (int): 预置点，C6设备预置点是1-12（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/preset/clear"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'index': index
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60006": "稍候再试",
            "60020": "确认设备是否支持该操作"
        }
        return self._handle_api_response(
            http_response,
            api_name="clear_device_preset",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def compose_panorama_image(
        self,
        device_serial: str,
        local_index: str
    ) -> Dict[str, Any]:
        """
        全景图片抓拍
        注：因图片存放在云录制空间，所以需要事先开通云录制。否则会失败。
        参考文档: 全景图片抓拍
        Args:
            device_serial (str): 设备序列号（必填）
            local_index (str): 资源号（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'compose_panorama_image' 仅限 'cn' 区域使用。", "区域限制错误")
        
        url = f"{self._base_url}/api/service/cloudrecord/pic/panoramic/compose"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'localIndex': local_index
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "400": "参数不正确",
            "404": "资源不存在",
            "500": "服务异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="compose_panorama_image",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def calibrate_ptz(
        self,
        device_serial: str,
        local_index: str = 1,
    ) -> Dict[str, Any]:
        """
        校准云台
        参考文档: 校准云台
        Args:
            device_serial (str): 设备序列号（必填）
            local_index (str): 通道号，ipc默认为1（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'calibrate_ptz' 仅限 'cn' 区域使用。", "区域限制错误")
        
        url = f"{self._base_url}/api/v3/device/ptz/manual/adjust"

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'localIndex': local_index
        }

        http_response = self._client._session.request('POST', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="calibrate_ptz",
            device_serial=device_serial,
            response_format="meta"
        )

    def reset_ptz(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        云台复位
        参考文档: 云台复位
        Args:
            device_serial (str): 设备序列号（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'reset_ptz' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/ctrl/ptz/reset"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, headers=headers)
        error_description_dict = {
            "10001": "参数为空或者格式不对",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20007": "参考服务中心排查方法",
            "20008": "设备响应超时，请检测设备网络或重试",
            "60020": "请确认设备是否支持该命令"
        }
        return self._handle_api_response(
            http_response,
            api_name="reset_ptz",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def control_ptz(
        self, 
        device_serial: str, 
        command: str, 
        action: str = "start", 
        speed: int = 1, 
        task_id: str = "default_task"
    ) -> Dict[str, Any]:
        """
        控制云台转动。
        适用于设备型号：CS-RK3-SWT1和CS-RK3-AWT1

        :param device_serial: 设备序列号
        :param command: 云台命令 (up, down, left, right, upleft, downleft, upright, downright)
        :param action: 动作 (start-开始, stop-结束)
        :param speed: 云台速度 (1~7)
        :param task_id: 任务ID
        :return: API响应的JSON数据
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'control_ptz' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/otap/action"

        headers = {
            "Content-Type": "application/json",
            "accessToken": self._client.access_token,
            "deviceSerial": device_serial,
            "localIndex": "0",
            "resourceCategory": "global",
            "domainIdentifier": "PTZManualCtrl",
            "actionIdentifier": "ModifyPTZCtrl"
        }

        payload = {
            "timeStamp": str(int(time.time() * 1000)), # 当前毫秒级时间戳
            "action": action,
            "control": "ptz",
            "command": command,
            "speed": speed,
            "taskID": task_id
        }

        http_response = self._client._session.request("PUT", url, headers=headers, json=payload)
        return self._handle_api_response(
            http_response,
            api_name="control_ptz",
            device_serial=device_serial,
            response_format="meta"
        )

    def capture_image(
        self, 
        device_serial: str, 
        channel_no: int, 
        quality: Optional[int]
    ) -> Dict[str, Any]:

        url = f"{self._base_url}/api/lapp/device/capture"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'quality': quality
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "10005": "appKey被冻结",
            "10051": "设备不属于当前用户或者未分享给当前用户",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁或者设备不支持萤石协议抓拍",
            "20032": "检查设备是否包含该通道",
            "49999": "接口调用异常",
            "60017": "设备返回失败",
            "60020": "请确认设备是否支持该命令"
        }
        return self._handle_api_response(
            http_response,
            api_name="capture_image",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_passenger_flow_switch_status(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        该接口用于获取客流统计开关状态（接口需要设备支持客流统计功能）
        参考文档: 获取客流统计开关状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_passenger_flow_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/passengerflow/switch/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "10005": "appKey被冻结",
            "10051": "设备不属于当前用户或者未分享给当前用户",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "请确认设备是否支持该命令"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_passenger_flow_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )
    
    def set_passenger_flow_switch(
        self,
        device_serial: str,
        enable: int,
        channel_no: Optional[int],
    ) -> Dict[str, Any]:
        """
        该接口用于设置客流统计开关（接口需要设备支持客流统计功能）
        参考文档: 设置客流统计开关
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 开关状态，1表示开启，0表示关闭（必填）
            channel_no (Optional[int]): 通道号，默认为1（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_passenger_flow_switch' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/passengerflow/switch/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持客流统计功能",
            "60022": "已是当前开关状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_passenger_flow_switch",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_daily_passenger_flow(
        self,
        device_serial: str,
        channel_no: int,
        date: str
    ) -> Dict[str, Any]:
        """
        该接口用于查询设备某一天的客流统计数据（接口需要设备支持客流统计功能）
        参考文档: 查询设备某一天的统计客流数据
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
            date (long): 时间戳日期，精确至毫秒，默认为今天，date参数只能是0时0点0分0秒（如1561046400000可以，1561050000000不行）（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_daily_passenger_flow' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/passengerflow/daily"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'date': date
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "请确认设备是否支持该命令"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_daily_passenger_flow",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_hourly_passenger_flow(
        self,
        device_serial: str,
        channel_no: int,
        date: str
    ) -> Dict[str, Any]:
        """
        该接口用于查询设备某一天每小时的客流统计数据（接口需要设备支持客流统计功能）
        参考文档: 查询设备某一天每小时的客流数据
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号（必填）
            date (long): 时间戳日期，精确至毫秒，默认为今天（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_hourly_passenger_flow' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/passengerflow/hourly"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no,
            'date': date
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "请确认设备是否支持该命令"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_hourly_passenger_flow",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def set_passenger_flow_config(
        self,
        device_serial: str,
        line: str,
        direction: int,
        channel_no: Optional[int]
    ) -> Dict[str, Any]:
        """
        该接口用于配置客流统计相关信息（接口需要设备支持客流统计功能）
        参考文档: 配置客流统计信息
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            line (str): 统计线的两个坐标点，坐标范围为0到1之间的7位浮点数，(0,0)坐标在左上角，格式如{"x1": "0.0","y1": "0.5","x2": "1","y2": "0.5"}（必填）
            direction (int): 指示方向的两个坐标点，(x1,y1)为起始点，(x2,y2)为结束点格式如{"x1": "0.5","y1": "0.5","x2": "0.5","y2": "0.6"}，最好与统计线保持垂直（必填）
            channel_no (Optional[int]): 非必选参数，不为空表示配置指定通道客流统计信息，为空表示配置设备本身信息（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_passenger_flow_config' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/passengerflow/config/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'line': line,
            'direction': direction
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "请确认设备是否支持该命令",
            "60022": "已是当前开关状态",
            "60025": "设备返回其他错误码"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_passenger_flow_config",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_passenger_flow_config(
        self,
        device_serial: str,
        channel_no: Optional[int]
    ) -> Dict[str, Any]:
        """
        该接口用于获取客流统计配置相关信息（接口需要设备支持客流统计功能）
        参考文档: 获取客流统计配置信息
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (Optional[int]): 非必选参数，不为空表示获取指定通道客流统计信息，为空表示获取设备本身信息（非必填）
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_passenger_flow_config' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/passengerflow/config/get"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_description_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken有效期为七天，建议在accessToken即将过期或者出现10002错误码的时候重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "请确认设备是否支持该命令",
            "60022": "已是当前开关状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_passenger_flow_config",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_description_dict
        )

    def get_device_otap_property(
        self,
        device_serial: str,
        local_index: str,
        resource_category: str,
        domain_identifier: str,
        prop_identifier: str
    ) -> Dict[str, Any]:
        """
        otap设备属性查询接口
        接口描述: 查询otap设备属性
        Args:
            device_serial (str): 设备序列号
            local_index (str): 资源序号
            resource_category (str): 资源种类，描述资源的类型
            domain_identifier (str): 功能点领域，填写报备时的属性所在领域
            prop_identifier (str): 功能点标识，填写报备时的属性标识符

        Raises:
            EZVIZAPIError: 当API调用失败时抛出。

        Returns:
            Dict[str, Any]: API返回的原始数据
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_otap_property' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/otap/prop"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'localIndex': local_index,
            'resourceCategory': resource_category,
            'domainIdentifier': domain_identifier,
            'propIdentifier': prop_identifier
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        error_description_dict = {
            "10001": "参数为空或者格式不对",
            "20007": "参考服务中心排查方法",
            "20018": "确认设备是否属于用户"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_otap_property",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def set_device_otap_property(
        self,
        device_serial: str,
        local_index: str,
        resource_category: str,
        domain_identifier: str,
        prop_identifier: str,
        property_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        OTAP设备属性设置接口。
        参考文档: OTAP设备属性设置接口
        Args:
            device_serial (str): 设备序列号
            local_index (str): 资源序号
            resource_category (str): 资源种类
            domain_identifier (str): 功能点领域
            prop_identifier (str): 功能点标识符
            property_data (Dict[str, Any]): 需要设置的属性数据，JSON结构。
        Returns:
            Dict[str, Any]: API返回的原始数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_otap_property' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/v3/device/otap/prop"

        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'localIndex': local_index,
            'resourceCategory': resource_category,
            'domainIdentifier': domain_identifier,
            'propIdentifier': prop_identifier,
            'Content-Type': 'application/json'
        }

        http_response = self._client._session.request('PUT', url, headers=headers, json=property_data)
        error_description_dict = {
            "10001": "参数为空或者格式不对",
            "20007": "参考服务中心排查方法",
            "20018": "确认设备是否属于用户"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_device_otap_property",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def execute_device_otap_action(
        self,
        device_serial: str,
        local_index: str,
        resource_category: str,
        domain_identifier: str,
        action_identifier: str,
        action_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        OTAP设备操作指令接口。
        参考文档: OTAP设备操作指令接口
        Args:
            device_serial (str): 设备序列号
            local_index (str): 资源序号
            resource_category (str): 资源种类
            domain_identifier (str): 功能点领域
            action_identifier (str): 功能点标识符
            action_data (Dict[str, Any]): 操作指令的数据，JSON结构。
        Returns:
            Dict[str, Any]: API返回的原始数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'execute_device_otap_action' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/v3/device/otap/action"

        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'localIndex': local_index,
            'resourceCategory': resource_category,
            'domainIdentifier': domain_identifier,
            'actionIdentifier': action_identifier,
            'Content-Type': 'application/json'
        }

        http_response = self._client._session.request('PUT', url, headers=headers, json=action_data)
        error_description_dict = {
            "10001": "参数为空或者格式不对",
            "20007": "参考服务中心排查方法",
            "20018": "确认设备是否属于用户"
        }
        return self._handle_api_response(
            http_response,
            api_name="execute_device_otap_action",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_description_dict
        )

    def get_voice_device_list(
        self,
        device_serial: str,
    ) -> Dict[str, Any]:
        """
        获取设备语音列表接口
        接口功能: 获取指定设备的语音列表，GET参数放在请求链接里
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_voice_device_list' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/route/voice/v3/devices/voices"

        params = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }

        http_response = self._client._session.request('GET', url, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_voice_device_list",
            device_serial=device_serial,
            response_format="meta"
        )
    
    def add_voice_to_device(
        self,
        device_serial: str,
        voice_name: str,
        voice_url: str
    ) -> Dict[str, Any]:
        """
        新增设备语音接口
        接口功能：将语音文件下发给设备，POST参数放在请求链接里
        Args:
            device_serial (str): 设备序列号
            voice_name (str): 设备语音名称
            voice_url (str): 语音文件url
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'add_voice_to_device' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/route/voice/v3/devices/voices"
        params = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'voiceName': voice_name,
            'voiceUrl': voice_url
        }
        http_response = self._client._session.request('POST', url, params=params)
        return self._handle_api_response(
            http_response,
            api_name="add_voice_to_device",
            device_serial=device_serial,
            response_format="meta"
        )     

    def modify_voice_name(
        self,
        device_serial: str,
        voice_id: int,
        voice_name: str,
        voice_url: str
    ) -> Dict[str, Any]:
        """
        修改设备语音名称接口
        接口功能：修改设备上的指定语音文件的语音名称，PUT参数放在请求链接里
        Args:
            device_serial (str): 设备序列号
            voicee_id (str): 设备语音唯一id
            voice_name (str): 设备语音名称
            voice_url (str): 语音文件url Y
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'modify_voice_name' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/route/voice/v3/devices/voices"
        params = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'voiceId': voice_id,
            'voiceName': voice_name,
            'voiceUrl': voice_url
        }
        http_response = self._client._session.request('PUT', url, params=params)
        return self._handle_api_response(
            http_response,
            api_name="modify_voice_name",
            device_serial=device_serial,
            response_format="meta"
        )
        
    def delete_voice_from_device(
        self,
        device_serial: str,
        voice_id: int,
        voice_name: str,
        voice_url: str
    ) -> Dict[str, Any]:
        """
        删除设备语音接口
        接口功能：删除设备上的指定语音文件，DELETE参数放在请求链接里
        Args:
            device_serial (str): 设备序列号
            voice_id (str): 设备语音唯一id
            voice_name (str): 设备语音名称
            voice_url (str): 语音文件url
        Returns:
            Dict[str, Any]: API返回的原始数据
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'delete_voice_from_device' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/route/voice/v3/devices/voices"
        params = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'voiceId': voice_id,
            'voiceName': voice_name,
            'voiceUrl': voice_url
        }
        http_response = self._client._session.request('DELETE', url, params=params)
        return self._handle_api_response(
            http_response,
            api_name="delete_voice_from_device",
            device_serial=device_serial,
            response_format="meta"
        )
    
    def set_device_alarm_sound(
        self,
        device_serial: str,
        enable: int,
        sound_type: int,
        voice_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置设备告警提示音。
        参考文档: 设备告警提示音设置接口
        Args:
            device_serial (str): 设备序列号（必填）
            enable (int): 0-关闭，1-开启（必填）
            sound_type (int): 0-短叫，1-长叫，2-静音，3-自定义语音（必填）
            voice_id (Optional[int]): 设备语音唯一id，soundType=3时有效（可选）
        Returns:
            Dict[str, Any]: API返回的原始数据，包含 'meta' 字段。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_alarm_sound' 仅限 'cn' 区域使用。", "区域限制错误")

        url = f"{self._base_url}/api/route/alarm/v3/devices/{device_serial}/alarm/sound"
        params = {
            'accessToken': self._client.access_token,
            'enable': enable,
            'soundType': sound_type
        }
        if voice_id is not None:
            params['voiceId'] = voice_id

        http_response = self._client._session.request('PUT', url, params=params)
        return self._handle_api_response(
            http_response,
            api_name="set_device_alarm_sound",
            device_serial=device_serial,
            response_format="meta"
        )        

    def transmit_isapi_command(
        self,
        isapi_path: str,
        method: Literal['GET', 'POST', 'PUT', 'DELETE'],
        device_serial: str,
        body: Optional[Union[str, Dict[str, Any]]] = None,
        content_type: str = "application/xml"
    ) -> Union[Dict[str, Any], str]:
        """
        ISAPI下行指令透传接口。
        该接口用于向海康品牌设备透传ISAPI协议指令。
        参考文档: ISAPI下行指令透传
        Args:
            isapi_path (str): ISAPI协议上的请求路径，例如 "/ISAPI/System/time/ntpServers/1"。
            method (Literal['GET', 'POST', 'PUT', 'DELETE']): HTTP请求方法。
            device_serial (str): 设备序列号。
            body (Optional[Union[str, Dict[str, Any]]]): 请求体。可以是XML字符串或JSON字典。对于GET请求通常为None。
            content_type (str): 请求体的内容类型，如 'application/xml' 或 'application/json'。默认为 'application/xml'。
        Returns:
            Union[Dict[str, Any], str]: API返回的数据。如果响应头指明是JSON，则返回字典；如果是XML或其他，则返回原始字符串。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
            ValueError: 当 method 参数不是支持的方法时抛出。
        """
        if method not in ('GET', 'POST', 'PUT', 'DELETE'):
            raise ValueError(f"不支持的HTTP方法: {method}。仅支持 'GET', 'POST', 'PUT', 'DELETE'。")

        # 构建完整的URL
        url = f"{self._base_url}/api/hikvision{isapi_path}"

        # 构建必需的请求头
        headers = {
            'EZO-AccessToken': self._client.access_token, # 注意：这里是 EZO-AccessToken，不是 accessToken
            'EZO-DeviceSerial': device_serial,
            'EZO-Date': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            'Content-Type': content_type
        }

        # 准备请求参数
        kwargs = {'headers': headers}

        # 根据method和body类型，选择传递data或json
        if body is not None:
            if isinstance(body, dict) and content_type == 'application/json':
                kwargs['json'] = body
            else:
                # 对于XML字符串或其他非字典类型，使用data
                kwargs['data'] = body

        try:
            # --- 核心改动：直接使用 client._session，绕过 client._request ---
            http_response = self._client._session.request(method, url, **kwargs)
            http_response.raise_for_status()

            # 从响应头中获取自定义返回码
            ezo_code = http_response.headers.get('EZO-Code')
            ezo_message = http_response.headers.get('EZO-Message', '未知错误')

            # 错误码映射表
            error_description_dict = {
                "10001": "参数为空或格式不正确",
                "10002": "accessToken异常或过期",
                "20002": "设备不存在",
                "20006": "网络异常",
                "20007": "设备不在线",
                "20008": "设备响应超时",
                "20018": "该用户不拥有该设备"
            }

            if ezo_code != '200':
                error_description = error_description_dict.get(ezo_code, "未知错误")
                raise EZVIZAPIError(ezo_code, ezo_message, error_description)

            # 请求成功，根据请求类型返回数据
            if content_type == 'application/json':
                return http_response.json()
            else:
                return http_response.text

        except requests.RequestException as e:
            if isinstance(e, requests.HTTPError):
                raise EZVIZAPIError(str(e.response.status_code), f"HTTP {e.response.status_code} 错误: {str(e)}", "")
            else:
                raise EZVIZAPIError("NETWORK_ERROR", f"网络请求失败: {str(e)}", "")


    def set_device_encrypt_off(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        关闭设备视频加密
        接口功能：根据设备验证码关闭设备视频加密开关
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
    
        url = f"{self._base_url}/api/lapp/device/encrypt/off"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20010": "检查设备验证码是否错误",
            "20018": "该用户不拥有该设备",
            "49999": "接口调用异常",
            "60016": "设备加密开关已是关闭状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_device_encrypt_off",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
    
    def set_device_encrypt_on(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        开启设备视频加密
        接口功能：开启设备视频加密开关
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/encrypt/on"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20010": "检查设备验证码是否错误",
            "20018": "该用户不拥有该设备",
            "49999": "接口调用异常",
            "60016": "设备加密开关已是关闭状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_device_encrypt_on",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
    
    def update_device_password(
        self, 
        device_serial: str, 
        old_password: str, 
        new_password: str
    ) -> Dict[str, Any]:
        """
        修改设备视频加密密码
        接口功能：该接口用于修改设备视频加密密码（设备重置后修改的密码失效）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            old_password (str): 设备旧的加密密码（必填）
            new_password (str): 设备新的加密密码，长度大超过12字节（必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/password/update"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'oldPassword': old_password,
            'newPassword': new_password
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20010": "检查设备验证码是否错误",
            "20018": "该用户不拥有该设备",
            "49999": "接口调用异常",
            "60012": "设备返回其他错误码",
            "60020": "确认设备是否支持修改视频预览密码"
        }
        return self._handle_api_response(
            http_response,
            api_name="update_device_password",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
    
    def set_device_defence(
        self, 
        device_serial: str, 
        is_defence: int
    ) -> Dict[str, Any]:
        """
        设置设备撤/布防
        接口功能：对设备布撤防状态进行修改（活动检测开关），实现布防和撤防功能，该接口需要设备支持能力集：support_defence
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            is_defence (int): 布防状态，0：撤防，1：布防（必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/defence/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'isDefence': is_defence
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "该用户不拥有该设备",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_device_defence",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
    
    def get_device_defence_plan(
        self, 
        device_serial: str, 
        channel_no: int
    ) -> Dict[str, Any]:
        """
        获取设备布撤防计划
        接口功能：获取设备布撤防计划，该接口需要设备支持能力集：support_defence
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (int): 通道号，默认为1（非必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/defence/plan/get"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "该用户不拥有该设备",
            "49999": "接口调用异常",
            "60020": "确认设备是否支持修改视频预览密码"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_defence_plan",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )  
    
    def set_device_defence_plan(
        self, 
        device_serial: str, 
        channel_no: Optional[int] = None, 
        start_time: Optional[str] = None,
        stop_time: Optional[str] = None,
        period: Optional[int] = None,
        enable: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置布撤防时间计划
        接口功能：该接口用于设置设备布撤防（活动检测）时间计划（需要设备支持布撤防计划）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (Optional[int]): 通道号，不传表示设备本身（必填）
            start_time (Optional[str]): 开始时间，如16:00，默认为00:00（非必填）
            stop_time (Optional[str]): 结束时间，如16:30;如果为第二天,在时间前加上n,如n00:00.结束时间必须在开始时间之后,间隔不能超过24个小时（非必填）
            period (Optional[int]): 周一~周日，用0~6表示，英文逗号分隔，默认为0,1,2,3,4,5,6（非必填）
            enable (Optional[int]): 是否启用：1-启用，0-不启用，默认为1（非必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/defence/plan/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        if channel_no:
            payload['channelNo'] = channel_no
        if start_time:
            payload['startTime'] = start_time
        if stop_time:
            payload['stopTime'] = stop_time
        if period:
            payload['period'] = period
        if enable:
            payload['enable'] = enable
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "该用户不拥有该设备",
            "49999": "接口调用异常",
            "60020": "确认设备是否支持修改视频预览密码"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_device_defence_plan",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
      
    def get_wifi_sound_switch_status(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取wifi配置提示音开关状态
        接口功能：该接口用于获取wifi配置或设备启动提示音开关状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """

        url = f"{self._base_url}/api/lapp/device/sound/switch/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持设置WIFI配置提示音开关功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_wifi_sound_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_wifi_sound_switch_status(
        self, 
        device_serial: str, 
        enable: int, 
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置wifi配置提示音开关
        接口功能：该接口用于设置wifi配置或设备启动提示音开关
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 状态：0-关闭，1-开启（必填）
            channel_no (Optional[int]): 通道号，不传表示设备本身（非必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。

        """
        url = f"{self._base_url}/api/lapp/device/sound/switch/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持设置WIFI配置提示音开关功能",
            "60022": "已是当前开关状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_wifi_sound_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
    
    def get_scene_switch_status(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取镜头遮蔽开关状态
        接口功能：该接口用于获取设备镜头遮蔽开关状态（需要设备支持镜头遮蔽功能）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填） 
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
    

        url = f"{self._base_url}/api/lapp/device/scene/switch/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持设置场景联动开关功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_scene_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_scene_switch_status(
        self, 
        device_serial: str, 
        enable: int, 
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置镜头遮蔽开关
        接口功能：该接口用于设置设备镜头遮蔽开关状态（需要设备支持镜头遮蔽功能）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 状态：0-关闭，1-开启（必填）
            channel_no (Optional[int]): 通道号，不传表示设备本身（非必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/scene/switch/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持镜头遮蔽功能",
            "60022": "已是当前开关状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_scene_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
      
    def get_ssl_switch_status(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取声源定位开关状态
        接口功能：该接口用于获取设备声源定位开关状态（需要设备支持声源定位功能）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/ssl/switch/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持声源定位功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_ssl_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_ssl_switch_status(
        self, 
        device_serial: str, 
        enable: int, 
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置声源定位开关
        接口功能：该接口用于设置设备声源定位开关状态（需要设备支持能力集：support_ssl）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 状态：0-关闭，1-开启（必填）
            channel_no (Optional[int]): 通道号，不传表示设备本身（非必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/device/ssl/switch/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持声源定位功能",
            "60022": "已是当前开关状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_ssl_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_indicator_light_switch_status(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取摄像机指示灯开关状态
        接口功能：该接口用于获取设备指示灯开关状态（需要设备支持指示灯功能）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        Returns:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_indicator_light_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/light/switch/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持声源定位功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_indicator_light_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
       
    def set_indicator_light_switch_status(
        self, 
        device_serial: str, 
        enable: int, 
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置摄像机指示灯开关
        接口功能：该接口用于设置摄像机指示灯开关状态（需要设备支持指示灯功能）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 状态：0-关闭，1-开启（必填）
            channel_no (Optional[int]): 通道号，不传表示设备本身（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_indicator_light_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/light/switch/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持指示灯设置功能",
            "60022": "已是当前开关状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_indicator_light_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_fullday_record_switch_status(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取全天录像开关状态
        接口功能：该接口用于获取设备全天录像开关状态（需要设备支持全天录像功能）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_fullday_record_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/fullday/record/switch/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持指示灯设置功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_fullday_record_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_fullday_record_switch_status(
        self, 
        device_serial: str, 
        enable: int, 
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置全天录像开关
        接口功能：该接口用于设置全天录像开关状态（需要设备支持全天录像功能）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 状态：0-关闭，1-开启（必填）
            channel_no (Optional[int]): 通道号，不传表示设备本身（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_fullday_record_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/fullday/record/switch/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no:
            payload['channelNo'] = channel_no
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持指示灯设置功能",
            "60022": "已是当前开关状态"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_fullday_record_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_motion_detection_sensitivity_config(
        self, 
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取移动侦测灵敏度配置
        接口功能：该接口用于获取智能算法配置（目前只支持移动侦测灵敏度配置）信息
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_motion_detection_sensitivity_config' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/algorithm/config/get"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持指示灯设置功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_motion_detection_sensitivity_config",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_motion_detection_sensitivity(
        self,
        device_serial: str,
        value: int,
        channel_no: Optional[int] = None,
        type: Optional[int] = 0
    ) -> Dict[str, Any]:
        """
        设置移动侦测灵敏度
        接口功能：该接口用于设置智能算法模式（目前只支持移动侦测灵敏度配置）
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            value (int): type为0时，该值为0~6，0表示灵敏度最低（必填）
            channel_no (Optional[int]): 通道号，不传表示设备本身（非必填）
            type (Optional[int]): 智能算法模式：0-移动侦测灵敏度。非必选，默认为0（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。  
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_motion_detection_sensitivity' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/algorithm/config/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'value': value
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
        if type is not None:
            payload['type'] = type

        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "20032": "该用户下通道不存在",
            "49999": "接口调用异常",
            "60020": "设备不支持指示灯设置功能",
            "60022": "已是当前灵敏度"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_motion_detection_sensitivity",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_sound_alarm(
        self,
        device_serial: str,
        type: int
    ) -> Dict[str, Any]:
        """
        设置告警声音模式
        接口功能：该接口用于设置告警声音模式
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            type (int): 声音类型：0-短叫，1-长叫，2-静音（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。  
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。

        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_sound_alarm' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/alarm/sound/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'type': type
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持指示灯设置功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_sound_alarm",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_offline_notify(
        self,
        device_serial: str,
        enable: int
    ) -> Dict[str, Any]:
        """
        开启或关闭设备下线通知
        接口功能：该接口用于开启或关闭设备下线通知
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 开启或关闭设备下线通知：0-关闭，1-开启（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。  
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_offline_notify' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/notify/switch"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持指示灯设置功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_offline_notify",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_sound_status(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取设备麦克风开关状态
        接口功能：该接口用于获取设备麦克风开关状态
        """
        url = f"{self._base_url}/api/lapp/camera/video/sound/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_sound_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_sound_status(
        self,
        device_serial: str,
        enable: str
    ) -> Dict[str, Any]:
        """
        设置设备麦克风开关状态
        接口功能：该接口用于设置麦克风开关状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (str): 开启或关闭麦克风：0-关闭，1-开启（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        url = f"{self._base_url}/api/lapp/camera/video/sound/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持设置麦克风功能"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_sound_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_mobile_status(
        self,
        device_serial: str,
        enable: str,
        channel_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置设备移动跟踪开关
        接口功能：该接口用于设置设备移动跟踪开关，需要设备支持能力集support_intelligent_track=1
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (str): 开启或关闭移动跟踪：0-关闭，1-开启（必填）
            channel_no (Optional[int]): 通道号（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_mobile_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/mobile/status/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no:
            payload['channelNo'] = channel_no

        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持移动跟踪"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_mobile_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_mobile_status(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取设备移动跟踪开关状态
        接口功能：该接口用于设置设备移动跟踪开关状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_mobile_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/mobile/status/get"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常",
            "60020": "设备不支持移动跟踪"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_mobile_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )
        
    def set_osd_name(
        self,
        device_serial: str,
        osd_name: str,
        channel_no: Optional[int] = 1
    ) -> Dict[str, Any]:
        """
        设置设备的osd名称
        接口功能：该接口用于设置设备osd名称(只用于支持osd设置的设备，需要设备支持能力集：support_osd=1)
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            osd_name (str): 需设置的osd内容（必填）
            channel_no (Optional[int]): 通道号,默认为1（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'update_osd_name' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/update/osd/name"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'osdName': osd_name,
            'channelNo': channel_no
        }
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_osd_name",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_osd_name(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询osd
        接口功能：查询设备osd
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出。
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_osd_name' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/osd"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, params=params, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_osd_name",
            device_serial=device_serial,
            response_format="code"
        )

    def get_intelligence_detection_switch_status(
        self,
        device_serial: str,
        type: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取设备智能检测开关状态
        接口功能：获取设备智能检测开关状态
        
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            type (Optional[int]): 智能检测开关类型 302-人体检测,304人脸抠图, 不传则代表画面变化检测（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_intelligence_detection_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/intelligence/detection/switch/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        if type is not None:
            payload['type'] = type
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_intelligence_detection_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_intelligence_detection_switch_status(
        self,
        device_serial: str,
        enable: str,
        channel_no: Optional[str] = None,
        type: Optional[str] = None
    ) -> Dict[str, Any]:
        """设置设备智能检测开关状态
        接口功能：设置设备智能检测开关状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (str): 状态： 0-关闭， 1-开启（必填）
            channel_no (Optional[str]): 通道号，非必选参数，不传表示设备本身（非必填）
            type (Optional[str]): 智能检测开关类型 302-人体检测,304人脸抠图, 不传则代表画面变化检测（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_intelligence_detection_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/intelligence/detection/switch/set"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'enable': enable
        }
        if channel_no is not None:
            payload['channelNo'] = channel_no
        if type is not None:
            payload['type'] = type
        http_response = self._client._session.request('POST', url, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10005": "appKey被冻结",
            "20002": "①设备没有注册到萤石云平台，请检查下设备网络参数，确保能正常连接网络②设备序列号不存在",
            "20006": "检查设备网络状况，稍后再试",
            "20007": "检查设备是否在线",
            "20008": "操作过于频繁，稍后再试",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_intelligence_detection_switch_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_human_track_switch(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """获取人形追踪开关状态
        接口功能：获取人形追踪开关状态接口
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_human_track_switch' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/switch/human/track"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        error_code_dict = {
            "10002": "accessToken异常或过期",
            "10031": "子账号没有设备权限",
            "20002": "设备不存在",
            "20006": "设备网络异常",
            "20007": "设备离线",
            "20008": "设备响应超时",
            "20018": "用户没有设备权限",
            "49999": "接口调用异常",
            "60020": "设备不支持"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_human_track_switch",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_code_dict
        )

    def set_human_track_switch(
        self,
        device_serial: str,
        enable: int
    ) -> Dict[str, Any]:
        """配置人形追踪开关状态
        接口功能：配置人形追踪开关接口
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 是否启用：1-启用，0-不启用（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_human_track_switch' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/switch/human/track"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        data = {
            'enable': enable
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=data)
        error_code_dict = {
            "10002": "accessToken异常或过期",
            "10031": "子账号没有设备权限",
            "20002": "设备不存在",
            "20006": "设备网络异常",
            "20007": "设备离线",
            "20008": "设备响应超时",
            "20018": "用户没有设备权限",
            "49999": "接口调用异常",
            "60020": "设备不支持"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_human_track_switch",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_code_dict
        )

    def set_system_operate(
        self,
        device_serial: str,
        system_operation: str,
        local_index: Optional[str] = None,
        delay: Optional[int] = None
    ) -> Dict[str, Any]:
        """发送系统操作命令（远程重启）
        接口功能：发送系统操作命令

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            system_operation (str): 系统操作命令：reboot-重启（必填）
            local_index (Optional[str]): 本地索引号（非必填）
            delay (Optional[int]): 延迟时间，单位秒，默认值0（非必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_system_operate' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/systemOperate"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        if local_index is not None:
            headers['localIndex'] = local_index
            
        payload = {
            'systemOperation': system_operation
        }
        if delay is not None:
            payload['delay'] = delay

        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10031": "http状态码403",
            "20007": "http状态码412",
            "20018": "http状态码403",
            "20032": "http状态码404"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_system_operate",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def set_timing_plan(
        self,
        device_serial: str,
        enable: str,
        start_time: str,
        end_time: str,
        week: str,
        event_arg: Optional[int] = 0,
    ) -> Dict[str, Any]:
        """
        工作模式计划设置
        接口功能：工作模式计划设置接口
        
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序
            enable (str): 计划状态 1-启用 0-不启用（必填）
            start_time (str): 每天的开始时间（必填）
            end_time (str): 每天的结束时间（必填）
            week (str): 每周重复（必填）
            event_arg (Optional[int]): 计划时间内执行的模式 0-省电模式 1-性能模式 2-常电模式 3-超级省电模式 ,计划时间外执行省电模式（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/timing/plan/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        payload = {
            'enable': enable,
            'startTime': start_time,
            'endTime': end_time,
            'week': week
        }
        # 不填默认为0
        if event_arg is not None:
            payload['eventArg'] = event_arg
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_timing_plan",
            device_serial=device_serial,
            response_format="code"
        )
    
    def get_timing_plan(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备工作模式计划
        接口功能：查询设备工作模式计划

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）

        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/timing/plan/get"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_timing_plan",
            device_serial=device_serial,
            response_format="code"
        )

    def open_human_detection_area(
        self,
        device_serial: str,
        type: str,
    ) -> Dict[str, Any]:
        """
        开启人形/PIR检测
        接口功能：开启人形/PIR检测
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            type (str): AI人形检测-1, PIR检测-5（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_alarm_detection_switch' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/alarm/detect/switch/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        payload = {
            'type': type
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="open_human_detection_area",
            device_serial=device_serial,
            response_format="code"
        )
    
    def set_pir_detection_area(
        self,
        device_serial: str,
        channel_no: str,
        area: str
    ) -> Dict[str, Any]:
        """
        设置PIR检测区域
        接口功能：设置PIR检测区域
        
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (str): 通道号（必填）
            area (str): 区域设置 ,如表顺序排列，每个值按位取值
                        例 [1,2,4,8,6] 则选中区域为序号（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_pir_detection_area' 仅限 'cn' 区域使用。", "区域限制错误")
        url =  f"{self._base_url}/api/v3/device/pir/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        payload = {
            'area': area
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_pir_detection_area",
            device_serial=device_serial,
            response_format="code"
        )

    def get_human_detection_area(
        self,
        device_serial: str,
        channel_no: str
    ) -> Dict[str, Any]:
        """
        查询人形检测区域
        接口功能：查询人形检测区域
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (str): 通道号（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/motion/detect/get"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_human_detection_area",
            device_serial=device_serial,
            response_format="code"
        )

    def set_human_detection_area(
        self,
        device_serial: str,
        channel_no: str,
        area: str
    ) -> Dict[str, Any]:
        """
        设置人形检测区域
        接口功能：设置人形检测区域
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (str): 通道号（必填）
            area (str): 区域设置 ,如表顺序排列，每个值按位取值
                        例 [1,2,4,8,6] 则选中区域为序号（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/motion/detect/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        payload = {
            'area': area
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_human_detection_area",
            device_serial=device_serial,
            response_format="code"
        )

    def get_device_detect_config(
        self,
        device_serial: str,
        channel_no: str
    ) -> Dict[str, Any]:
        """
        获取检测灵敏度
        接口功能：查询灵敏度信息

        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (str): 通道号（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_detect_config' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/detect/config/get"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_detect_config",
            device_serial=device_serial,
            response_format="code"
        )

    def set_device_detect_config(
        self,
        device_serial: str,
        channel_no: str,
        type: str,
        value: str
    ) -> Dict[str, Any]:
        """
        设置检测灵敏度
        设置灵敏度信息(只用于支持检测灵敏度设置的设备，需要设备支持能力集：support_sensibility_adjust=1)
        
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (str): 通道号（必填）
            type (str): 3-PIR检测灵敏度,4-人形检测灵敏度（必填）
            value (str): 取值为1-100,1表示灵敏度最低（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_detect_config' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/detect/config/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        payload = {
            'type': type,
            'value': value
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_detect_config",
            device_serial=device_serial,
            response_format="code"
        )
    
    def set_device_display_mode(
        self,
        device_serial: str,
        mode: str
    ) -> Dict[str, Any]:
        """
        设置设备图像风格
        接口功能：设置设备图像风格
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            mode (str): 图像风格参数,1-标准，2-写实，3-艳丽（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_display_mode' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/display/mode/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        payload = {
            'deviceSerial': device_serial,
            'mode': mode
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_display_mode",
            device_serial=device_serial,
            response_format="code"
        )

    def get_device_display_mode(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询图像风格
        接口功能：查询图像风格
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 '' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/display/mode/get"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_display_mode",
            device_serial=device_serial,
            response_format="code"
        )
    
    def set_device_work_mode(
        self,
        device_serial: str,
        mode: str
    ) -> Dict[str, Any]:
        """
        设置设备工作模式
        接口功能：设置设备工作模式
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            mode (str): 工作模式 0-省电模式 1-性能模式 2-常电模式 3-超级省电模式（必填）
        
        return: 
            Dict[str, Any]: API返回的JSON数据。
            
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/battery/work/mode/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        payload = {
            'mode': mode
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_work_mode",
            device_serial=device_serial,
            response_format="code"
        )

    def get_device_work_mode(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备工作模式
        接口功能：查询设备工作模式
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_work_mode' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/battery/work/mode/get"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_work_mode",
            device_serial=device_serial,
            response_format="code"
        )
    
    def get_device_power_status(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询电池充电状态
        接口功能：查询电池充电状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_power_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/power/status/get"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_power_status",
            device_serial=device_serial,
            response_format="code"
        )

    def set_device_switch_status(
        self,
        device_serial: str,
        enable: str,
        type: str
    ) -> Dict[str, Any]:
        """
        平台向设备设置各种开关量
        接口功能：平台向设备设置各种开关量,用于设置灯光提醒开关。
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (str): 开关状态,0-关闭，1-打开（必填）
            type (str): 开关类型,301-灯光闪烁开关/移动侦测灯光联动,305-灯光联动开关/PIR灯光联动（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/switchStatus/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        payload = {
            'enable': enable,
            'type': type
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_switch_status",
            device_serial=device_serial,
            response_format="code"
        )

    def get_device_switch_status(
        self,
        device_serial: str,
        channel_no: str,
        type: str
    ) -> Dict[str, Any]:
        """
        查询开关状态
        接口功能：查询开关状态,用于查询灯光提醒开关状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            channel_no (str): 通道号（必填）
            type (str): 301-灯光闪烁开关/移动侦测灯光联动,305-灯光联动开关/PIR灯光联动（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/switchStatus/get"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        params = {
            'type': type
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_switch_status",
            device_serial=device_serial,
            response_format="code"
        )

    def get_advanced_alarm_detection_types(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询高级告警侦测类型
        接口功能：查询高级告警侦测类型
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_advanced_alarm_detection_types' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/das/device/detect/switch/get"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_advanced_alarm_detection_types",
            device_serial=device_serial,
            response_format="code"
        )
    
    def get_device_format_status(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        设备存储介质状态查询接口
        接口文档：根据设备序列号查询设备上存储介质的状态信息
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/format/status"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        error_code_dict = {
            "10031": "子账号没有设备权限",
            "20002": "设备不存在",
            "20007": "设备不在线",
            "20011": "设备不支持或者设备异常",
            "60058": "设备存在高风险需要确权"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_format_status",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_code_dict
        )

    def format_device_disk(
        self,
        disk_index: str,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        设备存储介质格式化接口
        接口文档：根据设备序列号和存储介质编号格式化指定编号的设备存储空间
        Args:
            disk_index (str): 存储介质编号（必填）
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/format/disk"
        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'diskIndex': disk_index,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        error_code_dict = {
            "10002": "accessToken异常或过期",
            "10031": "子账号没有设备权限",
            "20002": "设备不存在",
            "20007": "设备不在线",
            "20011": "设备不支持或者设备异常",
            "20014": "存储介质不存在",
            "20016": "当前设备正在格式化",
            "20018": "用户没有设备权限",
            "60058": "设备存在高风险需要确权"
        }
        return self._handle_api_response(
            http_response,
            api_name="format_device_disk",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_code_dict
        )

    def set_video_level(
        self,
        local_index: str,
        device_serial: str,
        video_level: str
    ) -> Dict[str, Any]:
        """
        设置视频清晰度
        接口功能：设置视频清晰度，向设备下发指令修改设备通道的清晰度设置 是否支持托管/子账号: 支持托管及子账号，权限为Config，设备通道级鉴权
        
        Args:
            local_index (str): 设备通道号（必填）
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            video_level (str): 设备视频清晰度等级 0-流畅 1-均衡 2-高清 3-超清（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_video_level' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/setVideoLevel"
        headers = {
            'localIndex': local_index,
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }

        payload = {
            'videoLevel': video_level
        }

        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "20001": "通道不存在",
            "20002": "设备不存在",
            "20007": "设备不在线",
            "20008": "设备响应超时",
            "50000": "服务异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_video_level",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_code_dict
        )

    def set_device_video_encode(
        self,
        device_serial: str,
        stream_type_in: str,
        resolution: str,
        video_frame_rate: str,
        interval_frame_i: Optional[str] = "100",
        video_bit_rate: Optional[str] = "13",
        pic_quality: Optional[str] = "2",
        encode_type: Optional[str] = "1",
        encode_complex: Optional[str] = "1",
        channel_no: Optional[str] = "1"
    ) -> Dict[str, Any]:
        """
        设备视频参数设置
        接口功能：通用设备视频参数设置接口，不保证所有参数生效所有设备（具体生效情况依赖设备支持程度）。 是否支持托管及子账号：支持，权限为Config
        Args:
            access_token (str): 访问令牌（必填）
            stream_type_in (str): 视频码流 1-主码流 2-子码流（必填）
            resolution (str): 视频分辨率 0-DCIF 1-CIF 2-QCIF 3-4CIF 4-2CIF 6-QVGA（320x240） 16-VGA 17-UXGA 18-SVGA 19-HD720p（必填）
            video_frame_rate (str): 视频帧率 0-全帧率 1-1/16 2-1/8 3-1/4 4-1/2 5-1 6-2 7-4 8-6 9-8 10-10 11-12 12-16 13-20 14-15 15-18 16-22（必填）
            interval_frame_i (str): I帧间隔 默认100 单位：秒（非必填）
            video_bit_rate (str): 码率上限 0-32K 1-48k 2-64K 3-80K 4-96K 5-128K 6-160k 7-192K 8-224K 9-256K 10-320K 11-384K 12-448K 13-512K 14-640K 15-768K 16-896K 17-1024K 18-1280K 19-1536K 20-1792K 21-2048K 22-自定义 默认13（非必填）
            pic_quality (str): 图像质量 0-最高 1-较高 2-中等 3-低 4-较低 5-最低 默认2（非必填）
            encode_type (str): 编码类型 1-H264 2-H265 默认1（非必填）
            encode_complex (str): 编码复杂度 0-低 1-中 2-高 默认1（非必填）
            device_serial (str): 设备序列号（必填）
            channel_no (str): 设备通道号 默认为1（非必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_video_encode' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/lapp/device/video/encode/set"
        params = {
            'accessToken': self._client.access_token,
            'streamTypeIn': stream_type_in,
            'resolution': resolution,
            'videoFrameRate': video_frame_rate,
            'intervalFrameI': interval_frame_i,
            'videoBitRate': video_bit_rate,
            'picQuality': pic_quality,
            'encodeType': encode_type,
            'encodeComplex': encode_complex,
            'deviceSerial': device_serial,
            'channelNo': channel_no
        }
        http_response = self._client._session.request('POST', url, params=params)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "10031": "子账号或开发者用户无权限",
            "20002": "设备不存在",
            "20007": "设备不在线",
            "20008": "设备响应超时",
            "20018": "托管账户没有权限",
            "50000": "服务器异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="set_device_video_encode",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_code_dict
        )

    def get_device_video_encode(
        self, 
        device_serial: str, 
        local_index: Optional[int] = 1,
        stream_type: Optional[int] = 1
    ) -> Dict[str, Any]:
        """
        设备视频参数查询
        接口文档：查询设备设置的视频相关参数
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            local_index (Optional[int]): 资源描述，描述资源类型下的序号（默认1）（非必填）
            stream_type (Optional[int]): 视频码流：1主码流、2子码流（默认1）（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_video_encode' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/encode/get"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'localIndex': str(local_index)
        }
        params = {
            'streamType': stream_type
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        error_code_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "accessToken异常或过期",
            "20002": "设备不存在",
            "20007": "设备不在线",
            "20015": "设备不支持",
            "20018": "该用户不拥有该设备",
            "70018": "资源不存在"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_video_encode",
            device_serial=device_serial,
            response_format="meta",
            error_code_map=error_code_dict
        )

    def set_device_audio_encode_type(
        self,
        device_serial: str,
        encode_type: str,
        local_index: Optional[str] = "1"
    ) -> Dict[str, Any]:
        """
        音频编码格式切换（PUT）
        接口功能：音频编码格式切换 是否支持托管：支持，权限为Config。 设备通道级鉴权，需要校验的能力集：support_audio_encode_types
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            encode_type (str): 音频编码格式 AAC（必填）
            local_index (Optional[str]): 资源（通道）号，非必选，默认为1（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_audio_encode_type' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/audio/encodeType"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        if local_index is not None:
            headers['localIndex'] = local_index
        payload = {
            'encodeType': encode_type
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_audio_encode_type",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_device_video_encode_type(
        self,
        device_serial: str,
        encode_type: str,
        stream_type: int,
        local_index: Optional[str] = 1
    ) -> Dict[str, Any]:
        """
        切换设备编码格式（PUT）
        接口功能：切换设备编码格式，校验的能力集：support_video_encode_switch_disable 为0 表示支持 是否支持托管及子账号：支持，权限为Config，设备通道级鉴权
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_video_encode_type' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/encodeType"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        if local_index is not None:
            headers['localIndex'] = local_index
        payload = {
            'encodeType': encode_type,
            'streamType': stream_type
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_video_encode_type",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_device_white_balance(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备白平衡参数（GET）
        功能：查询设备白平衡参数， 托管/子账号：支持， 权限类型：设备级GET权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_white_balance' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/white/balance"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_white_balance",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_device_white_balance(
        self,
        device_serial: str,
        mode: str,
        white_balance_red: Optional[str] = None,
        white_balance_blue: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        设置设备白平衡参数（PUT）
        功能：设置设备白平衡参数， 托管/子账号：支持， 权限类型：设备级Config权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            mode (str): 白平衡模式，枚举值[auto：自动；lock：锁定；manul：手动]（必填）
            white_balance_red (Optional[str]): 白平衡红增益，手动模式下生效且手动模式下必传，范围0-255（非必填）
            white_balance_blue (Optional[str]): 白平衡蓝增益，手动模式下生效且手动模式下必传，范围0-255（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_white_balance' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/white/balance"
        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'mode': mode
        }
        if white_balance_red is not None:
            payload['whiteBalanceRed'] = white_balance_red
        if white_balance_blue is not None:
            payload['whiteBalanceBlue'] = white_balance_blue
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_white_balance",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_device_backlight_compensation(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备背光补偿参数（GET）
        功能：查询设备背光补偿参数， 托管/子账号：支持， 权限类型：设备级GET权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_backlight_compensation' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/blc"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_backlight_compensation",
            device_serial=device_serial,
            response_format="meta"
        )
    
    def set_device_backlight_compensation(
        self,
        device_serial: str,
        mode: str
    ) -> Dict[str, Any]:
        """
        设置设备背光补偿参数（PUT）
        功能：设置设备背光补偿参数， 托管/子账号：支持， 权限类型：设备级Config权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            mode (str): 背光补偿模式，枚举值[close-关闭；up-上；down-下；left-左；right-右；center-中心]（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_backlight_compensation' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/blc"
        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'mode': mode
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_backlight_compensation",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_device_denoising(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备图像降噪参数（GET）
        功能：查询设备图像降噪参数， 托管/子账号：支持， 权限类型：设备级GET权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_denoising' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/image/denoising"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_denoising",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_device_denoising(
        self,
        device_serial: str,
        mode: str,
        general_level: Optional[int] = None,
        spatial_level: Optional[int] = None,
        temporal_level: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置设备图像降噪参数（PUT）
        功能：设置设备图像降噪参数， 托管/子账号：支持， 权限类型：设备级Config权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            mode (str): 降噪模式，枚举值[close-关闭；general-普通；advanced-专家]（必填）
            general_level (Optional[int]): 普通模式降噪等级，普通模式下必填，范围1-100（非必填）
            spatial_level (Optional[int]): 专家模式空域等级，专家模式下必填，范围1-100（非必填）
            temporal_level (Optional[int]): 专家模式时域等级，专家模式下必填，范围1-100（非必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_denoising' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/image/denoising"
        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'mode': mode
        }
        if general_level is not None:
            payload['generalLevel'] = general_level
        if spatial_level is not None:
            payload['spatialLevel'] = spatial_level
        if temporal_level is not None:
            payload['temporalLevel'] = temporal_level

        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_denoising",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_device_exposure_time(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备曝光时间参数（GET）
        功能：查询设备曝光时间参数， 托管/子账号：支持， 权限类型：设备级GET权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_exposure_time' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/exposure/time"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params = params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_exposure_time",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_device_exposure_time(
        self,
        device_serial: str,
        exposure_target: int
    ) -> Dict[str, Any]:
        """
        设置设备曝光时间参数（PUT）
        功能：设置设备曝光时间参数， 托管/子账号：支持， 权限类型：设备级Config权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            exposure_target (int): 曝光时间，单位us，范围：1-40000（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_exposure_time' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/exposure/time"

        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'exposureTarget': exposure_target
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_exposure_time",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_device_anti_flicker(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备防闪烁参数（GET）
        功能：查询设备防闪烁参数， 托管/子账号：支持， 权限类型：设备级GET权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_anti_flicker' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/anti/flicker"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, params=params, headers = headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_anti_flicker",
            device_serial=device_serial,
            response_format="meta"
        )
    
    def set_device_anti_flicker(
        self,
        device_serial: str,
        mode: str
    ) -> Dict[str, Any]:
        """
        设置设备防闪烁参数（PUT）
        功能：设置设备防闪烁参数， 托管/子账号：支持， 权限类型：设备级Config权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            mode (str): 防闪烁模式，枚举值：[50Hz，60Hz]（必填）.
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_anti_flicker' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/anti/flicker"
        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'mode': mode
        }
        http_response = self._client._session.request('PUT', url, data=payload, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="set_device_anti_flicker",
            device_serial=device_serial,
            response_format="meta"
        )
    
    def get_device_disk_capacity(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备存储空间
        本接口仅适用于设备型号：ZNQXSXJ01ES系列和ZNBQSXJ01ES系列设备。其余型号不保证可用。
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return: 
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_disk_capacity' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/diskCapacity"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, params=params, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_disk_capacity",
            device_serial=device_serial,
            response_format="code"
        )

    def set_device_video_switch_status(
        self,
        device_serial: str,
        type: int,
        enable: int
    ) -> Dict[str, Any]:
        """
        设置设备视频类开关状态（PUT）
        接口文档：设置设备视频类开关状态，支持托管及子账号,校验权限为Config，设备级鉴权。隐私遮蔽开关设置需要设备支持support_privacy能力集, 休眠开关设置需要设备支持support_low_power能力集，视频水印是否展示logo开关状态查询需要设备支持support_logo_switch能力集。
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            type (int): 开关类型，7.隐私遮蔽 21.休眠 702.视频水印是否展示LOGO（必填）
            enable (int): 设备开关状态，0.关闭，1.开启（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_video_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/switch/status"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        payload = {
            'type': type,
            'enable': enable
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_video_switch_status",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_device_video_switch_status(
        self,
        device_serial: str,
        type: int
    ) -> Dict[str, Any]:
        """
        查询设备视频类开关状态（GET）
        接口文档：查询设备视频类开关状态，支持托管及子账号,校验权限为GET，设备级鉴权。隐私遮蔽开关设置需要设备支持support_privacy能力集, 休眠开关设置需要设备支持support_low_power能力集，视频水印是否展示logo开关状态查询需要设备支持support_logo_switch能力集。
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            type (int): 开关类型，7.隐私遮蔽 21.休眠 702.视频水印是否展示LOGO（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_video_switch_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/switch/status"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        params = {
            'type': type
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_video_switch_status",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_fill_light_mode(
        self,
        device_serial: str,
        mode: int = 0
    ) -> Dict[str, Any]:
        """
        设置补光灯模式
        接口文档：设置补光灯模式
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            mode (int): “黑白夜视”模式:0；
                        “全彩夜视”模式:1；
                        “智能夜视”:2；
                        人形检测全彩模式:3；
                        默认为0（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/fillLight/mode"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'mode': mode
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_fill_light_mode",
            device_serial=device_serial,
            response_format="code"
        )

    def set_fill_light_switch(
        self,
        device_serial: str,
        enable: int = 0
    ) -> Dict[str, Any]:
        """
        设置补光灯开关
        接口文档：设置补光灯开关
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            enable (int): 状态：0-关闭，1-开启； 默认为0（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_fill_light_switch' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/fillLight/switch/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial
        }
        if enable is not None:
            payload['enable'] = enable
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_fill_light_switch",
            device_serial=device_serial,
            response_format="code"
        )

    def set_talk_speaker_volume(
        self,
        device_serial: str,
        volume: int
    ) -> Dict[str, Any]:
        """
        配置音量
        接口文档：配置音量
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            volume (int): 音量值，范围0-100（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_talk_speaker_volume' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/talkSpeakerVolume"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'volume': volume
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_talk_speaker_volume",
            device_serial=device_serial,
            response_format="code"
        )

    def get_talk_speaker_volume(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询音量
        接口文档：查询音量
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_talk_speaker_volume' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/talkSpeakerVolume"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="get_talk_speaker_volume",
            device_serial=device_serial,
            response_format="code"
        )

    def get_device_alarm_detect_switch(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询人形/PIR检测状态
        接口文档：查询人形/PIR检测状态
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_alarm_detect_switch' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/alarm/detect/switch/get"
        headers = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers)
        return self._handle_api_response(
            http_response,
            api_name="get_device_alarm_detect_switch",
            device_serial=device_serial,
            response_format="code"
        )

    def set_device_defense(
        self,
        device_serial: str,
        status: int
    ) -> Dict[str, Any]:
        """
        设备主动防御（DeviceDefence）
        接口说明:操作设备开启/关闭设备主动防御，需要设备支持support_active_defense能力集
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            status (int): 主动防御状态，0-关闭，1-开启（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_defense' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/defence"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial,
            'status': status
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_defense",
            device_serial=device_serial,
            response_format="code"
        )

    def play_device_audition(
        self,
        device_serial: str,
        voice_index: int,
        volume: int
    ) -> Dict[str, Any]:
        """
        播放铃声
        接口文档：播放铃声
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            voice_index (int): 语音索引（必填）
            volume (int): 音量（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/v3/device/audition"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'voiceIndex': voice_index,
            'volume': volume
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="play_device_audition",
            device_serial=device_serial,
            response_format="code"
        )

    def set_detect_switch(
        self,
        disk_capacity: str,
        type: Optional[int] = 0
    ) -> Dict[str, Any]:
        """
        设置侦测开关
        接口文档：设置侦测开关
        Args:
            disk_capacity (str): 设备序列号（必填）
            type (Optional[int]): 0-关闭;
                                  4-活动侦测;
                                  8-人形检测;
                                  默认为0（非必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.

        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_detect_switch' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/detect/switch/set"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'diskCapacity': disk_capacity
        }
        if type:
            payload['type'] = type
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_detect_switch",
            device_serial=disk_capacity,  # 使用disk_capacity作为设备标识
            response_format="code"
        )

    def get_device_image_params(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备图像参数（GET）
        功能：查询设备图像参数， 托管/子账号：支持， 权限类型：设备级GET权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_image_params' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/video/image/params"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_image_params",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_device_image_params(
        self,
        device_serial: str,
        gammaCorrection: int,
        gain: int,
        imageStyle: str,
        brightness: Optional[int] = None,
        contrast: Optional[int] = None,
        saturatio: Optional[int] = None,
        sharpness: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        设置设备图像参数
        功能：设置设备图像参数， 托管/子账号：支持， 权限类型：设备级Config权限，该接口需要设备支持能力集：support_image_param
        Args:
            device_serial (str): 设备序列号,存在英文字母的设备序列号，字母需为大写（必填）
            gammaCorrection (int): 伽马矫正，范围0-9（必填）
            gain (int): 增益，范围0-100（必填）
            imageStyle (str): 图像风格，[standard-标准；soft-柔和；gorgeous-艳丽；manual-手动]（必填）
            brightness (Optional[int]): 亮度，范围0-100,手动模式下必填（非必填）
            contrast (Optional[int]): 对比度，范围0-100,手动模式下必填（非必填）
            saturatio (Optional[int]): 饱和度，范围0-100,手动模式下必填（非必填）
            sharpness (Optional[int]): 锐度，范围0-100,手动模式下必填（非必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_device_image_params' 仅限 'cn' 区域使用。", "区域限制错误")
        if imageStyle == "manual":
            if brightness is None or contrast is None or saturatio is None or sharpness is None:
                raise ValueError("当imageStyle为manual时，brightness、contrast、saturatio、sharpness为必填参数")
        url = f"{self._base_url}/api/v3/device/video/image/params"
        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'gammaCorrection': gammaCorrection,
            'gain': gain,
            'imageStyle': imageStyle
        }
        if brightness is not None:
            payload['brightness'] = brightness
        if contrast is not None:
            payload['contrast'] = contrast
        if saturatio is not None:
            payload['saturatio'] = saturatio
        if sharpness is not None:
            payload['sharpness'] = sharpness

        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_device_image_params",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_ptz_homing_point(
        self,
        device_serial: str,
        channel_no: int,
        key: str
    ) -> Dict[str, Any]:
        """
        查询设备归位点模式（GET）
        功能：支持托管及子账号，权限为Config，需要设备支持support_ptz_homing_point能力级
        Args:
            key (str): 固定传值returnToPoint（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_ptz_homing_point' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/keyValue/{device_serial}/{channel_no}/op"
        params = {
            'accessToken': self._client.access_token,
            'key': key
        }
        http_response = self._client._session.request('GET', url, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_ptz_homing_point",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_ptz_homing_point(
        self,
        device_serial: str,
        channel_no: int,
        key: str,
        value: str
    ) -> Dict[str, Any]:
        """
        设置设备归位点模式（PUT）
        功能：支持托管及子账号，权限为Config，需要设备支持support_ptz_homing_point能力级
        Args:
            key (str): 固定值returnToPoint（必填）
            value (str): 归位点模式 0.默认归位点模式 1.自定义归位点模式（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_ptz_homing_point' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/keyValue/{device_serial}/{channel_no}/op"
        payload = {
            'accessToken': self._client.access_token,
            'key': key,
            'value': value
        }
        http_response = self._client._session.request('PUT', url, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_ptz_homing_point",
            device_serial=device_serial,
            response_format="meta"
        )
    
    def get_ptz_homing_point_status(
        self,
        device_serial: str,
        channel_no: int,
        key: str
    ) -> Dict[str, Any]:
        """
        查询自定义归位点设置状态（GET）
        功能：支持托管及子账号，权限为Config，通道级鉴权，需要设备支持support_ptz_homing_point能力级
        Args:
            key (str): 固定值preset（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_ptz_homing_point_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/keyValue/{device_serial}/{channel_no}/op"
        params = {
            'accessToken': self._client.access_token,
            'key': key
        }
        http_response = self._client._session.request('GET', url , params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_ptz_homing_point_status",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_preset_point(
        self,
        device_serial: str,
        channel_no: int,
        key: str,
        value: str
    ) -> Dict[str, Any]:
        """
        设置自定义归位点（PUT）
        功能：支持托管及子账号，权限为Config，需要设备支持support_ptz_homing_point能力级
        Args:
            key (str): 固定值preset（必填）
            value (str): 自定义归位点设置状态 1.是 0.否（必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_preset_point' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/keyValue/{device_serial}/{channel_no}/op"
        payload = {
            'accessToken': self._client.access_token,
            'key': key,
            'value': value
        }
        http_response = self._client._session.request('PUT', url, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_preset_point",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_intelligent_model_device_support(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        查询设备支持算法列表
        接口功能：查询指定设备支持的智能算法列表
        Args:
            device_serial (str): 设备序列号
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_intelligent_model_device_support' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/intelligent/model/device/support"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_intelligent_model_device_support",
            device_serial=device_serial,
            response_format="meta"
        )
        
    def get_intelligent_model_device_list(
        self,
        device_serial: Optional[str] = None,
        page_start: Optional[int] = 0,
        page_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        查询智能设备列表
        接口功能：查询智能设备列表（设备上已加载的算法）
        Args:
            device_serial (Optional[str]): 关键字查询 分页参数与设备序列号两者 只可输入其一（非必填）
            page_start (Optional[int]): 页码，从0开始，默认为0（非必填）
            page_size (Optional[int]): 单页数量（单页限制数量8~50个）（非必填）
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_intelligent_model_device_list' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/intelligent/model/device"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        params = {}
        if device_serial:
            params['deviceSerial'] = device_serial
        if page_start is not None:
            params['pageStart'] = page_start
        if page_size is not None:
            params['pageSize'] = page_size
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_intelligent_model_device_list",
            device_serial=device_serial or "unknown",
            response_format="meta"
        )
    
    def load_intelligent_model_app(
        self,
        device_serial: str,
        app_id: str
    ) -> Dict[str, Any]:
        """
        设备智能算法下发
        接口功能：设备智能算法下发
        
        Args:
            device_serial (str): 设备序列号
            app_id (str): 算法ID
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'load_intelligent_model_app' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/intelligent/model/app/load"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'appId': app_id
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="load_intelligent_model_app",
            device_serial=device_serial,
            response_format="meta"
        )

    def set_intelligent_model_device_onoffline(
        self,
        device_serial: str,
        app_id: str,
        status: str
    ) -> Dict[str, Any]:
        """
        设备启用/停用智能算法
        接口功能：设备启用/停用智能算法，如果需要卸载算法，需要先停用算法，若设备内存不足会自动卸载已停用算法
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'set_intelligent_model_device_onoffline' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/intelligent/model/device/onoffline"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'appId': app_id,
            'status': status
        }
        http_response = self._client._session.request('PUT', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="set_intelligent_model_device_onoffline",
            device_serial=device_serial,
            response_format="meta"
        )
       
    def get_device_version_info(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取设备版本信息
        接口文档：查询用户下指定设备的版本信息
        Args:
            device_serial (str): 设备序列号
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/lapp/device/version/info"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="get_device_version_info",
            device_serial=device_serial,
            response_format="code"
        )

    def upgrade_device_firmware(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        设备升级固件
        接口功能：升级设备固件至最新版本
        Args:
            device_serial (str): 设备序列号
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/lapp/device/upgrade"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="upgrade_device_firmware",
            device_serial=device_serial,
            response_format="code"
        )

    def get_device_upgrade_status(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取设备升级状态
        接口文档：查询用户下指定设备的升级状态，包括升级进度。
        Args:
            device_serial (str): 设备序列号
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        url = f"{self._base_url}/api/lapp/device/upgrade/status"
        payload = {
            'accessToken': self._client.access_token,
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('POST', url, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="get_device_upgrade_status",
            device_serial=device_serial,
            response_format="code"
        )

    def get_device_upgrade_modules(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取设备模块升级信息
        接口功能：查询待升级的模块信息。触发模块升级前调用该接口，用于确认哪些模块需要升级
        Args:
            device_serial (str): 设备序列号
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_upgrade_modules' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/service/device/upgrade/modules"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_upgrade_modules",
            device_serial=device_serial,
            response_format="meta"
        )

    def upgrade_device_modules(
        self,
        device_serial: str,
        modules: str
    ) -> Dict[str, Any]:
        """
        触发设备模块升级
        接口功能：升级设备模块。模块信息来源于获取设备模块升级信息的接口
        Args:
            device_serial (str): 设备序列号
            modules (str): 模块信息列表
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'upgrade_device_modules' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/v3/device/upgrade/modules"
        headers = {
            'accessToken': self._client.access_token
        }
        payload = {
            'deviceSerial': device_serial,
            'modules': modules
        }
        http_response = self._client._session.request('POST', url, headers=headers, data=payload)
        return self._handle_api_response(
            http_response,
            api_name="upgrade_device_modules",
            device_serial=device_serial,
            response_format="meta"
        )

    def get_device_module_upgrade_status(
        self,
        device_serial: str,
        module: str
    ) -> Dict[str, Any]:
        """
        获取设备模块升级状态
        接口功能：用于获取设备模块升级状态及进度
        Args:
            device_serial (str): 设备序列号
            module (str): 模块名称
        return:
            Dict[str, Any]: API返回的JSON数据。
        Raises:
            EZVIZAPIError: 当API调用失败时抛出.
        """
        if self._client.region != "cn":
            raise EZVIZAPIError("403", "函数 'get_device_module_upgrade_status' 仅限 'cn' 区域使用。", "区域限制错误")
        url = f"{self._base_url}/api/service/device/upgrade/modules/status"
        headers = {
            'accessToken': self._client.access_token
        }
        params = {
            'deviceSerial': device_serial,
            'module': module
        }
        http_response = self._client._session.request('GET', url, headers=headers, params=params)
        return self._handle_api_response(
            http_response,
            api_name="get_device_module_upgrade_status",
            device_serial=device_serial,
            response_format="meta"
        )
