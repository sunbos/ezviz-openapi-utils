class EZVIZBaseError(Exception):
    """萤石开放平台基础异常类"""
    def __init__(self, code: str, msg: str, description: str = ""):
        self.code = code
        self.msg = msg
        self.description = description
        super().__init__(f"Code {code}: {msg} - {description}")

class EZVIZAuthError(EZVIZBaseError):
    """萤石开放平台认证相关异常"""
    pass

class EZVIZAPIError(EZVIZBaseError):
    """萤石开放平台API调用异常"""
    pass

class EZVIZDeviceNotSupportedError(EZVIZBaseError):
    """设备不支持该功能的异常"""
    def __init__(self, code: str, msg: str, device_serial: str = "", api_name: str = ""):
        self.device_serial = device_serial
        self.api_name = api_name
        description = f"设备 {device_serial} 不支持功能 {api_name}: {msg}"
        super().__init__(code, msg, description)
