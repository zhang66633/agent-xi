---
name: 部署检查
description: 部署前检查清单：环境变量、依赖、配置文件、数据库迁移
keywords: [部署, deploy, 上线, 发布, 检查]
category: 运维
---

## 执行步骤

1. 检查 `.env` 和 `.env.example` 是否一致（所有必需变量都有值）
2. 使用 `execute_shell` 运行 `pip list --outdated` 检查过时依赖
3. 检查 `docker-compose.yml` 和 `Dockerfile` 配置是否正确
4. 使用 `git_log` 查看待部署的提交
5. 检查数据库迁移文件是否存在
6. 输出部署检查报告
