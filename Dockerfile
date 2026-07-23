# ─── Stage 1: 构建前端 ───────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --silent
COPY web/ ./
RUN npm run build

# ─── Stage 2: 运行后端 ───────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# 配置文件
COPY config/ ./config/

# 前端静态文件（从构建阶段复制）
COPY --from=frontend-build /app/web/dist ./web/dist

# 数据目录
RUN mkdir -p .data

EXPOSE 9731

CMD ["python", "-m", "agent_xi.server", "--host", "0.0.0.0"]
