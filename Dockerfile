FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates jq libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 获取 llama.cpp 最新非 draft tag，下载 ubuntu-x64 CPU 版预编译包
RUN LATEST=$(curl -sL "https://api.github.com/repos/ggerganov/llama.cpp/releases?per_page=10" \
        | jq -r '[.[] | select(.draft == false)][0].tag_name') \
    && echo "llama.cpp tag: ${LATEST}" \
    && curl -L -f -o /tmp/llama.tar.gz \
       "https://github.com/ggerganov/llama.cpp/releases/download/${LATEST}/llama-${LATEST}-bin-ubuntu-x64.tar.gz" \
    && mkdir -p /opt/llama \
    && tar -xzf /tmp/llama.tar.gz -C /opt/llama --strip-components=1 \
    && rm -f /tmp/llama.tar.gz \
    && LD_LIBRARY_PATH=/opt/llama /opt/llama/llama-server --version

# 关键：llama-server 和它的 .so 都在 /opt/llama，一起加进 PATH 和 LD_LIBRARY_PATH
ENV PATH=/opt/llama:$PATH \
    LD_LIBRARY_PATH=/opt/llama

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY start.py .
COPY api_wrapper.py .
COPY models/ ./models/
COPY build/ ./build/

ENV PORT=8000
EXPOSE 8000

CMD ["python", "-u", "start.py"]
