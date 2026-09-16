#!/usr/bin/env python3
# api_wrapper.py - 统一入口：serve 前端 + 标准 OpenAI API
#
# - GET  /                       → 前端页面（build/index.html）
# - GET  /<path>                 → 前端静态资源 / SPA fallback
# - GET  /v1/models              → 标准 OpenAI 格式（仅 shaoyu）
# - GET  /v1/models/{id}         → 单个模型信息
# - POST /v1/chat/completions    → 透传到 llama-server
# - GET  /health                 → 健康检查
#
# 用法:
#   python api_wrapper.py
#   python api_wrapper.py --port 9001 --upstream http://127.0.0.1:9000 --static ./build
import os
import argparse
import requests
from flask import (
    Flask, request, jsonify, Response,
    stream_with_context, send_from_directory,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)

# 由 main() 填充
UPSTREAM = "http://127.0.0.1:9000"
STATIC_DIR = os.path.join(SCRIPT_DIR, "build")

# 对外声明的模型列表
MODELS = [
    {
        "id": "shaoyu",
        "object": "model",
        "created": 1735689600,
        "owned_by": "local",
    },
]


# ==================== 静态文件（前端） ====================
@app.route('/')
def index():
    index_path = os.path.join(STATIC_DIR, 'index.html')
    if os.path.isfile(index_path):
        return send_from_directory(STATIC_DIR, 'index.html')
    return jsonify({
        "service": "Shaoyu API Wrapper",
        "upstream": UPSTREAM,
        "note": f"前端未找到 ({STATIC_DIR})",
    })


@app.route('/<path:filename>')
def static_file(filename):
    # /v1/* 交给 API 处理，其他当静态文件
    if filename.startswith('v1/'):
        return jsonify({
            "error": {
                "message": "not found",
                "type": "invalid_request_error",
            }
        }), 404

    full_path = os.path.join(STATIC_DIR, filename)
    if os.path.isfile(full_path):
        return send_from_directory(STATIC_DIR, filename)

    # SPA fallback
    index_path = os.path.join(STATIC_DIR, 'index.html')
    if os.path.isfile(index_path):
        return send_from_directory(STATIC_DIR, 'index.html')

    return jsonify({"error": {"message": "not found"}}), 404


# ==================== 标准 OpenAI API ====================
@app.route('/v1/models', methods=['GET', 'OPTIONS'])
def list_models():
    if request.method == 'OPTIONS':
        return '', 204
    return jsonify({"object": "list", "data": MODELS})


@app.route('/v1/models/<model_id>', methods=['GET', 'OPTIONS'])
def get_model(model_id):
    if request.method == 'OPTIONS':
        return '', 204
    for m in MODELS:
        if m["id"] == model_id:
            return jsonify(m)
    return jsonify({
        "error": {
            "message": f"The model '{model_id}' does not exist",
            "type": "invalid_request_error",
            "param": "model",
            "code": "model_not_found",
        }
    }), 404


@app.route('/v1/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy(path):
    if request.method == 'OPTIONS':
        return '', 204

    url = f"{UPSTREAM}/v1/{path}"

    # 转发请求头（去掉 hop-by-hop 字段）
    skip_headers = {'host', 'content-length', 'connection', 'accept-encoding'}
    headers = {k: v for k, v in request.headers if k.lower() not in skip_headers}

    # 判断是否流式
    is_stream = False
    if request.is_json:
        data = request.get_json(silent=True) or {}
        is_stream = bool(data.get('stream', False))

    try:
        upstream_resp = requests.request(
            method=request.method,
            url=url,
            headers=headers,
            params=request.args,
            data=request.get_data(),
            stream=True,
            timeout=(10, 300),
        )
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": {
                "message": f"upstream error: {e}",
                "type": "api_error",
            }
        }), 502

    # 流式响应：逐块透传
    if is_stream:
        def generate():
            try:
                for chunk in upstream_resp.iter_content(chunk_size=None):
                    if chunk:
                        yield chunk
            finally:
                upstream_resp.close()

        return Response(
            stream_with_context(generate()),
            status=upstream_resp.status_code,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            },
        )

    # 非流式：直接返回
    return Response(
        upstream_resp.content,
        status=upstream_resp.status_code,
        headers={
            'Content-Type': upstream_resp.headers.get('Content-Type', 'application/json'),
        },
    )


# ==================== 健康检查 ====================
@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "upstream": UPSTREAM,
        "static": STATIC_DIR,
        "models": [m["id"] for m in MODELS],
    })


def main():
    global UPSTREAM, STATIC_DIR
    parser = argparse.ArgumentParser(description="Shaoyu 统一入口")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--upstream", default="http://127.0.0.1:9000")
    parser.add_argument("--static", default=os.path.join(SCRIPT_DIR, "build"))
    args = parser.parse_args()

    UPSTREAM = args.upstream
    STATIC_DIR = args.static

    print("=" * 60)
    print("  🔌 Shaoyu 统一入口")
    print("=" * 60)
    print(f"  监听:        http://{args.host}:{args.port}")
    print(f"  转发到:      {UPSTREAM}")
    print(f"  静态目录:    {STATIC_DIR}")
    print(f"  前端页面:    http://{args.host}:{args.port}/")
    print(f"  OpenAI API:  http://{args.host}:{args.port}/v1")
    print(f"  模型名:      {', '.join(m['id'] for m in MODELS)}")
    print("=" * 60)

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
