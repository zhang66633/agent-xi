---
name: 测试生成
description: 为指定函数或模块自动生成 pytest 单元测试
keywords: [测试, test, pytest, 单元测试, 用例]
category: 开发
---

## 执行步骤

1. 使用 `read_file` 读取目标代码
2. 识别所有可测试的函数/方法
3. 为每个函数生成测试用例：
   - 正常输入
   - 边界值
   - 异常情况
   - 空输入
4. 使用 `write_file` 或 `edit_file` 写入测试文件
5. 使用 `execute_shell` 运行 `pytest` 验证测试通过

## 输出格式

生成的测试文件应遵循项目现有的测试风格（参考 `tests/` 目录）。
使用 pytest fixtures，mock 外部依赖。
