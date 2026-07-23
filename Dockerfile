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

# Python 依赖（清华源加速）
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e . -i https://pypi.tuna.tsinghua.edu.cn/simple

# 配置文件
COPY config/ ./config/

# 前端静态文件（从构建阶段复制）
COPY --from=frontend-build /app/web/dist ./web/dist

# 数据目录
RUN mkdir -p .data

EXPOSE 9731

CMD ["python", "-m", "agent_xi.server", "--host", "0.0.0.0"]
