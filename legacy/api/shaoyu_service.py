# api/shaoyu_service.py —— 少羽模型推理服务
from threading import Thread
from transformers import TextIteratorStreamer

from model_loader import model, tokenizer, DEVICE


def get_response(prompt, history=None, max_new_tokens=100,
                 temperature=0.8, top_k=40, top_p=0.9):
    """非流式：一次性返回完整回答"""
    reply_chunks = []
    for chunk in get_response_stream_generator(
        prompt, history, max_new_tokens, temperature, top_k, top_p
    ):
        if chunk == '[DONE]':
            break
        reply_chunks.append(chunk)
    return ''.join(reply_chunks)


def get_response_stream_generator(prompt, history=None, max_new_tokens=100,
                                  temperature=0.8, top_k=40, top_p=0.9):
    """流式：逐个 token yield 文本片段，最后 yield '[DONE]'"""
    messages = []
    if history:
        for user_msg, bot_msg in history:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": bot_msg})
    messages.append({"role": "user", "content": prompt})

    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(DEVICE)

    streamer = TextIteratorStreamer(
        tokenizer, skip_prompt=True, skip_special_tokens=True
    )

    generation_kwargs = dict(
        **inputs,
        max_new_tokens=int(max_new_tokens),
        temperature=float(temperature),
        top_k=int(top_k),
        top_p=float(top_p),
        do_sample=True,
        repetition_penalty=1.1,
        eos_token_id=tokenizer.eos_token_id,
        streamer=streamer,
    )

    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()

    for new_text in streamer:
        if new_text:
            yield new_text

    thread.join()
    yield '[DONE]'