FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# 下载 llama.cpp 预编译二进制
ARG LLAMA_VERSION=b4585
RUN curl -L -o /tmp/llama.zip \
    "https://github.com/ggerganov/llama.cpp/releases/download/${LLAMA_VERSION}/llama-${LLAMA_VERSION}-bin-ubuntu-x64.zip" \
    && unzip /tmp/llama.zip -d /opt/llama \
    && find /opt/llama -name "llama-server" -exec cp {} /usr/local/bin/ \; \
    && chmod +x /usr/local/bin/llama-server \
    && rm -rf /tmp/llama.zip

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_wrapper.py .
COPY models/ ./models/
COPY build/ ./build/

ENV PORT=8000
EXPOSE 8000

CMD ["python", "-c", "\
import subprocess, sys, time, os; \
p1 = subprocess.Popen(['llama-server', '-m', 'models/shaoyu-q4_k_m.gguf', \
    '--alias', 'shaoyu', '--host', '127.0.0.1', '--port', '9000', \
    '-c', '2048', '--no-webui']); \
time.sleep(5); \
p2 = subprocess.Popen([sys.executable, '-u', 'api_wrapper.py', \
    '--host', '0.0.0.0', '--port', os.environ.get('PORT', '8000'), \
    '--upstream', 'http://127.0.0.1:9000', '--static', 'build']); \
p2.wait()"]
