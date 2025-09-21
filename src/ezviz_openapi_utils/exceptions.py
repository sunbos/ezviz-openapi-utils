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