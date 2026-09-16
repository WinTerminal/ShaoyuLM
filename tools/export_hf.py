#!/usr/bin/env python3
# export_hf.py - 把 .pth state_dict 导出为 HuggingFace 格式目录
# 用法: python export_hf.py --out ./hf_model
import os
import shutil
import argparse
import torch
from transformers import AutoTokenizer
from model_minimind import MiniMindForCausalLM, MiniMindConfig

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pth", default=os.path.join(SCRIPT_DIR, "full_sft_512.pth"))
    parser.add_argument("--tokenizer", default=os.path.join(SCRIPT_DIR, "tokenizer"))
    parser.add_argument("--out", default=os.path.join(SCRIPT_DIR, "hf_model"))
    parser.add_argument("--dtype", default="float16", choices=["float16", "float32"])
    args = parser.parse_args()

    print(f"📂 pth:       {args.pth}")
    print(f"📂 tokenizer: {args.tokenizer}")
    print(f"📂 输出:      {args.out}")
    print(f"📂 dtype:     {args.dtype}")
    print()

    # 1. 构建 config（与底座一致）
    config = MiniMindConfig(
        hidden_size=512,
        num_hidden_layers=10,
        intermediate_size=1408,
        num_key_value_heads=2,
        num_attention_heads=8,
        vocab_size=6400,
        use_moe=False,
        max_position_embeddings=32768,
        tie_word_embeddings=True,
    )

    # 2. 构建空模型并加载权重
    print("🏗️  构建模型...")
    model = MiniMindForCausalLM(config)

    print("💾 加载 state_dict...")
    state = torch.load(args.pth, map_location="cpu", weights_only=True)
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing:
        print(f"⚠️  missing keys: {len(missing)} 个（前 5 个: {missing[:5]}）")
    if unexpected:
        print(f"⚠️  unexpected keys: {len(unexpected)} 个（前 5 个: {unexpected[:5]}）")

    # 3. 转 dtype
    dtype = torch.float16 if args.dtype == "float16" else torch.float32
    model = model.to(dtype).eval()

    # 4. 保存为 HuggingFace 格式
    os.makedirs(args.out, exist_ok=True)
    print(f"💾 保存到 {args.out} ...")
    model.save_pretrained(args.out, safe_serialization=False)

    # 5. 拷 tokenizer 文件
    print("📦 拷贝 tokenizer ...")
    for fname in os.listdir(args.tokenizer):
        src = os.path.join(args.tokenizer, fname)
        dst = os.path.join(args.out, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"   + {fname}")

    # 6. 确保 chat_template 写进 tokenizer_config.json
    tok = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    jinja = os.path.join(args.tokenizer, "chat_template.jinja")
    if os.path.exists(jinja) and not getattr(tok, "chat_template", None):
        with open(jinja, "r", encoding="utf-8") as f:
            tok.chat_template = f.read()
    tok.save_pretrained(args.out)

    # 7. 校验
    print()
    print("=" * 60)
    print("✅ 导出完成")
    print("=" * 60)
    print(f"目录: {args.out}")
    for f in sorted(os.listdir(args.out)):
        p = os.path.join(args.out, f)
        if os.path.isfile(p):
            size_mb = os.path.getsize(p) / 1024 / 1024
            print(f"  {f:40s}  {size_mb:.2f} MB")
    print()
    print("下一步:")
    print(f"  python llama.cpp/convert_hf_to_gguf.py {args.out} \\")
    print(f"    --outtype f16 --outfile shaoyu-f16.gguf")


if __name__ == "__main__":
    main()
