# app.py - Flask 主应用
# 提供 /v1/chat/completions 和 /api/v1/chat/completions 两套路径，
# 与 llama-server 行为一致，前端可以无缝切换后端。
import os
import json
import time
import uuid
import traceback
from flask import Flask, request, jsonify, Response, stream_with_context

from model_loader import model, tokenizer, DEVICE
from api import api as api_bp
from api.shaoyu_service import get_response, get_response_stream_generator

app = Flask(__name__, static_folder='./build', static_url_path='/')
app.register_blueprint(api_bp, url_prefix='/api')


# ==================== OpenAI 兼容核心 ====================
MODELS = [
    {"id": "shaoyu", "object": "model", "created": 1735689600, "owned_by": "local"},
    {"id": "shaoyu-512", "object": "model", "created": 1735689600, "owned_by": "local"},
]


def _openai_chunk(content="", finish_reason=None, model="shaoyu"):
    delta = {}
    if content:
        delta["content"] = content
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def _chat_completions_impl():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": {"message": "invalid json"}}), 400

    messages = data.get("messages", [])
    stream = bool(data.get("stream", False))
    model_name = data.get("model", "shaoyu")
    max_tokens = int(data.get("max_tokens", 100))
    temperature = float(data.get("temperature", 0.8))
    top_p = float(data.get("top_p", 0.9))
    top_k = int(data.get("top_k", 40))

    if not messages:
        return jsonify({"error": {"message": "messages is required"}}), 400

    prompt = None
    for m in reversed(messages):
        if m.get("role") == "user":
            prompt = m.get("content", "")
            break
    if prompt is None:
        return jsonify({"error": {"message": "no user message"}}), 400

    history = []
    for i in range(len(messages) - 1):
        if messages[i].get("role") == "user" and messages[i + 1].get("role") == "assistant":
            history.append([messages[i]["content"], messages[i + 1]["content"]])

    if not stream:
        reply = get_response(prompt, history=history,
                             max_new_tokens=max_tokens, temperature=temperature,
                             top_k=top_k, top_p=top_p)
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": reply},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    gen = get_response_stream_generator(prompt, history=history,
                                        max_new_tokens=max_tokens, temperature=temperature,
                                        top_k=top_k, top_p=top_p)

    @stream_with_context
    def sse_events():
        for delta in gen:
            if delta == '[DONE]':
                yield "data: " + json.dumps(_openai_chunk("", "stop", model_name), ensure_ascii=False) + "\n\n"
                yield "data: [DONE]\n\n"
                break
            if not delta:
                continue
            yield "data: " + json.dumps(_openai_chunk(delta, None, model_name), ensure_ascii=False) + "\n\n"

    resp = Response(sse_events(), mimetype="text/event-stream")
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Connection'] = 'keep-alive'
    return resp


# ==================== 路由注册（两套路径，同一实现） ====================
@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def v1_chat_completions():
    if request.method == 'OPTIONS':
        return '', 204
    return _chat_completions_impl()


@app.route('/api/v1/chat/completions', methods=['POST', 'OPTIONS'])
def api_v1_chat_completions():
    if request.method == 'OPTIONS':
        return '', 204
    return _chat_completions_impl()


@app.route('/v1/models', methods=['GET', 'OPTIONS'])
def v1_models():
    if request.method == 'OPTIONS':
        return '', 204
    return jsonify({"object": "list", "data": MODELS})


@app.route('/')
def index():
    return app.send_static_file('index.html')


if __name__ == '__main__':
    host = os.environ.get("SHAOYU_HOST", "0.0.0.0")
    port = int(os.environ.get("SHAOYU_PORT", "9000"))
    print(f"server:      http://{host}:{port}")
    print(f"openai root: http://{host}:{port}/v1/chat/completions")
    print(f"openai api:  http://{host}:{port}/api/v1/chat/completions")
    app.run(host=host, port=port, debug=False, threaded=True)
