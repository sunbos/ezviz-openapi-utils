# 为 EZVIZ OpenAPI Utils 做贡献

感谢您对为 EZVIZ OpenAPI Utils 库做贡献的兴趣！本文档提供了设置开发环境、运行测试和提交贡献的指南和说明。

## 开发环境设置

### 先决条件

- Python 3.7 或更高版本
- Git
- 有效的 `app_key` 和 `app_secret`（从萤石开放平台的账号中心 → 应用信息 → 应用密钥获取）

### 环境设置

1. 在 GitHub 上 Fork 代码仓库

2. 在本地克隆您的 Fork：

   ```bash
   git clone https://github.com/your-username/ezviz-openapi-utils.git
   cd ezviz-openapi-utils
   ```

3. 创建虚拟环境（推荐）：

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

4. 以开发模式安装包及其测试依赖：

   ```bash
   pip install -e .[dev]
   ```

### 配置

在仓库根目录创建 `.env` 文件，填入您的 EZVIZ API 凭据：

```env
EZVIZ_APP_KEY=your_app_key_here
EZVIZ_APP_SECRET=your_app_secret_here
```

**重要提示**：切勿将 `.env` 文件或凭据提交到版本控制。`.gitignore` 文件已经排除了 `.env` 文件。

## 运行测试

### 测试结构

- `tests/test_client.py`：Client 类测试（认证、令牌管理）
- `tests/test_api.py`：EZVIZOpenAPI 类测试（API 方法）
- `tests/test_oauth.py`：OAuth 令牌处理测试

### 测试执行

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_client.py

# 运行测试并显示详细输出
pytest -v

# 运行测试并显示覆盖率（如果已安装 coverage）
pytest --cov=src/ezviz_openapi_utils
```

**注意**：如果未配置 `.env` 文件或缺少凭据，需要 API 凭据的集成测试将自动跳过。

## 代码风格和质量

### 格式化

- 遵循 PEP 8 风格指南
- 使用一致的缩进（4 个空格）
- 尽可能保持行长度在 88 个字符以内

### 类型提示

- 为所有函数参数和返回类型使用类型提示
- 利用 `TypedDict` 处理 API 响应结构（如现有代码库所示）

### 文档

- 为所有公共函数和类添加 Google 风格的文档字符串
- 添加新功能时更新 README.md 和 README.zh-CN.md
- 保持注释清晰简洁

## 进行更改

### 分支管理

1. 为您的功能或错误修复创建新分支：

   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

### 提交消息

- 使用描述性的提交消息
- 适当时遵循常规提交格式：
  - `feat: 添加设备控制的新 API 方法`
  - `fix: 处理 Client 类中的令牌过期问题`
  - `docs: 更新 README 中的新示例`
  - `test: 为设备管理添加集成测试`

### 代码更改

- 确保您的更改不会破坏现有功能
- 为新功能或错误修复添加测试
- 根据需要更新类型提示和文档

## 提交拉取请求

1. **提交前**：

   - 运行所有测试确保通过
   - 验证代码遵循风格指南
   - 如有必要，更新文档

2. **创建 PR**：

   - 访问 GitHub 上的您的 Fork
   - 点击 "Compare & pull request"
   - 填写 PR 模板，包括：
     - 对更改的清晰描述
     - 要解决的问题（如适用）
     - 任何破坏性更改
     - 相关问题（如有）

3. **PR 要求**：

   - 所有测试必须通过
   - 维护者的代码审查批准
   - 清晰且描述性的提交历史

## API 方法实现指南

如果您要向 `EZVIZOpenAPI` 类添加新的 API 方法：

1. **方法结构**：

   ```python
   def your_api_method(self, param1: str, param2: Optional[int] = None) -> YourResponseType:
       """方法功能的简要描述。

       Args:
           param1: param1 的描述
           param2: param2 的描述（可选）

       Returns:
           YourResponseType: 返回值的描述

       Raises:
           EZVIZAPIError: 如果 API 返回错误
       """
       # 实现代码
   ```

2. **错误处理**：

   - 始终检查 API 响应码
   - 为非 200 响应引发适当的 `EZVIZAPIError` 异常
   - 包含 API 响应中的错误码和消息

3. **类型安全**：

   - 为复杂的 API 响应定义 `TypedDict` 结构
   - 为参数和返回值使用适当的类型提示

## 报告问题

如果您发现错误或有功能请求：

1. 检查[问题跟踪器](https://github.com/sunbos/ezviz-openapi-utils/issues)中是否已存在该问题

2. 如果没有，[创建新问题](https://github.com/sunbos/ezviz-openapi-utils/issues/new)

3. 包括：

   - 问题或功能请求的清晰描述
   - 复现步骤（针对错误）
   - 期望行为 vs 实际行为（针对错误）
   - 您的环境详情（Python 版本、操作系统等）

## 许可证

通过为本项目做贡献，您同意您的贡献将根据[MIT 许可证](LICENSE)进行授权。