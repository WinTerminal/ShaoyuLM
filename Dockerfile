FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates jq \
    && rm -rf /var/lib/apt/lists/*

# 动态获取 llama.cpp 最新非 draft tag（含 pre-release）
RUN LATEST=$(curl -sL "https://api.github.com/repos/ggerganov/llama.cpp/releases?per_page=10" \
        | jq -r '[.[] | select(.draft == false)][0].tag_name') \
    && echo "llama.cpp tag: ${LATEST}" \
    && curl -L -f -o /tmp/llama.tar.gz \
       "https://github.com/ggerganov/llama.cpp/releases/download/${LATEST}/llama-${LATEST}-bin-ubuntu-x64.tar.gz" \
    && mkdir -p /opt/llama \
    && tar -xzf /tmp/llama.tar.gz -C /opt/llama \
    && find /opt/llama -name "llama-server" -exec cp {} /usr/local/bin/ \; \
    && chmod +x /usr/local/bin/llama-server \
    && rm -rf /tmp/llama.tar.gz

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
