# Source: origin/main at 25cd41321d244592b4f5c9250b13443e5502129d

def get_device_info(
        self,
        device_serial: str,
    ) -> Dict[str, Any]:
        """
        获取单个设备信息
        接口功能: 查询用户下指定设备的基本信息。

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

        error_remark_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "",
            "20014": "",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_info",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_remark_dict
        )

def list_devices_by_page(
        self,
        page_start: Optional[int] = 0,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        分页查询设备列表（POST）
        接口功能: 分页查询设备列表。起始页从0开始，不超过400页；每页默认查询数默认为10，不超过50。

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
        error_remark_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10004": "用户不存在",
            "10005": "appKey被冻结",
            "49999": "接口调用异常"
        }

        return self._handle_api_response(
            http_response,
            api_name="list_devices_by_page",
            response_format="code",
            error_code_map=error_remark_dict
        )

def list_devices_by_id(
        self,
        start_id: str,
        page_size: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        根据设备索引id分页查询设备列表（POST）
        接口功能: 根据起始索引分页查询设备列表。每页默认查询数默认为10，不超过50。

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
        error_remark_dict = {
            "10001": "无效参数",
            "10002": "accessToken过期或异常",
            "10004": "用户不存在",
            "10005": "appKey异常",
            "49999": "数据异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="list_devices_by_id",
            device_serial="",
            response_format="code",
            error_code_map=error_remark_dict
        )

def get_device_camera_list(
        self,
        device_serial: str
    ) -> Dict[str, Any]:
        """
        获取指定设备的通道信息
        接口功能: 获取指定设备的通道信息。

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
        error_remark_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "",
            "20014": "",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_camera_list",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_remark_dict
        )

def get_device_status(
        self,
        device_serial: str,
        channel_no: Optional[int] = 1
    ) -> Dict[str, Any]:
        """
        获取设备状态信息
        接口功能: 该接口用于根据序列号通道号获取设备状态信息。

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
        error_remark_dict = {
            "10001": "参数为空或格式不正确",
            "10002": "重新获取accessToken",
            "10005": "appKey被冻结",
            "20002": "",
            "20014": "",
            "20018": "检查设备是否属于当前账户",
            "49999": "接口调用异常"
        }
        return self._handle_api_response(
            http_response,
            api_name="get_device_status",
            device_serial=device_serial,
            response_format="code",
            error_code_map=error_remark_dict
        )
