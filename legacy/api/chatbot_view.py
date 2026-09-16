import json
import time
import uuid
import traceback
from flask import request, jsonify, Response, stream_with_context

from . import api
from .shaoyu_service import get_response, get_response_stream_generator


# ==================== 模型列表 ====================
MODELS = [
    {
        "id": "shaoyu",
        "object": "model",
        "created": 1735689600,
        "owned_by": "local",
    },
    {
        "id": "shaoyu-512",
        "object": "model",
        "created": 1735689600,
        "owned_by": "local",
    },
]


@api.route('/v1/models', methods=['GET', 'OPTIONS'])
def list_models():
    if request.method == 'OPTIONS':
        return '', 204
    return jsonify({"object": "list", "data": MODELS})


@api.route('/v1/models/<model_id>', methods=['GET', 'OPTIONS'])
def get_model(model_id):
    if request.method == 'OPTIONS':
        return '', 204
    for m in MODELS:
        if m["id"] == model_id:
            return jsonify(m)
    return jsonify({"error": {"message": f"model '{model_id}' not found", "type": "invalid_request_error"}}), 404


# ==================== OpenAI 兼容聊天接口 ====================
def _openai_chunk(content="", finish_reason=None, model="shaoyu"):
    delta = {}
    if content:
        delta["content"] = content
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }


@api.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def chat_completions():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": {"message": "invalid json", "type": "invalid_request_error"}}), 400

    messages = data.get("messages", [])
    stream = bool(data.get("stream", False))
    model_name = data.get("model", "shaoyu")
    max_tokens = int(data.get("max_tokens", 100))
    temperature = float(data.get("temperature", 0.8))
    top_p = float(data.get("top_p", 0.9))
    top_k = int(data.get("top_k", 40))

    if not messages:
        return jsonify({"error": {"message": "messages is required", "type": "invalid_request_error"}}), 400

    prompt = None
    for m in reversed(messages):
        if m.get("role") == "user":
            prompt = m.get("content", "")
            break
    if prompt is None:
        return jsonify({"error": {"message": "no user message", "type": "invalid_request_error"}}), 400

    history = []
    for i in range(len(messages) - 1):
        if messages[i].get("role") == "user" and messages[i + 1].get("role") == "assistant":
            history.append([messages[i]["content"], messages[i + 1]["content"]])

    # ---------- 非流式 ----------
    if not stream:
        reply = get_response(
            prompt, history=history,
            max_new_tokens=max_tokens, temperature=temperature,
            top_k=top_k, top_p=top_p,
        )
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    # ---------- 流式 ----------
    gen = get_response_stream_generator(
        prompt, history=history,
        max_new_tokens=max_tokens, temperature=temperature,
        top_k=top_k, top_p=top_p,
    )

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


# ==================== 旧接口（向后兼容） ====================
@api.route('/chat/get_ai_response', methods=['POST'])
def get_ai_response():
    try:
        user_input = request.json['user_input']
        ai_response = get_response(user_input)
        return jsonify({'ai_response': ai_response})
    except Exception:
        traceback.print_exc()
        return {'err': 'server_error'}


@api.route('/chat/get_ai_response_stream', methods=['GET'])
def get_ai_response_stream():
    try:
        user_input = request.args.get('user_input')
        if not user_input:
            return Response("data: [DONE]\n\n", mimetype="text/event-stream")

        history_str = request.args.get('history', '[]')
        try:
            history = json.loads(history_str)
        except Exception:
            history = []

        gen = get_response_stream_generator(user_input, history=history)

        @stream_with_context
        def sse_events():
            for delta in gen:
                if delta == '[DONE]':
                    yield "data: [DONE]\n\n"
                    break
                if not delta:
                    continue
                yield "data: " + json.dumps({"t": delta}, ensure_ascii=False) + "\n\n"

        response = Response(sse_events(), mimetype="text/event-stream")
        response.headers['Content-Encoding'] = 'identity'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'
        return response
    except Exception:
        traceback.print_exc()
        return {'err': 'server_error'}
