# 使用官方Python镜像
FROM python:3.8-slim

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY . /app

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口5000
EXPOSE 5000

# 运行应用程序
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
