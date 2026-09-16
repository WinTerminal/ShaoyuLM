#!/usr/bin/env python3
# tools/package.py - 打包 ShaoyuLM 为 zip
#
# 用法:
#   python tools/package.py                    完整打包（q4_k_m + f16 + pth）
#   python tools/package.py --lite             精简打包（仅 q4_k_m）
#   python tools/package.py --no-models        只打包代码
#   python tools/package.py --output xxx.zip   自定义输出
import os
import argparse
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(SCRIPT_DIR, "models")

PACKAGE_INCLUDE = [
    "run_all.py",
    "api_wrapper.py",
    "README.md",
    "LICENSE",
    "requirements.txt",
    "pyproject.toml",
    "build",
    "legacy",
    "tools",
]

EXCLUDE_PARTS = {
    "__pycache__",
    ".venv", "venv",
    "node_modules",
    ".git", ".DS_Store",
    ".pytest_cache", ".mypy_cache",
    "hf_model",
}

EXCLUDE_SUFFIX = (".pyc", ".log", ".zip")

# 三档模型集
# 注: full_sft_512.pth 在 legacy/ 目录下，会随 legacy/ 自动打包
MODEL_SETS = {
    "full": ("shaoyu-q4_k_m.gguf", "shaoyu-f16.gguf"),
    "lite": ("shaoyu-q4_k_m.gguf",),
    "none": (),
}


def _should_exclude(relpath):
    parts = set(relpath.replace("\\", "/").split("/"))
    if parts & EXCLUDE_PARTS:
        return True
    if relpath.endswith(EXCLUDE_SUFFIX):
        return True
    return False


def package(output, mode="full", quiet=False):
    out_path = os.path.join(SCRIPT_DIR, output)
    if os.path.exists(out_path):
        os.remove(out_path)

    def log(m):
        if not quiet:
            print(f"[package] {m}", flush=True)

    models = MODEL_SETS[mode]
    log(f"输出: {output}")
    log(f"模式: {mode}（{len(models)} 个模型）")

    added = 0
    missing = []

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. 代码 / 前端 / 工具
        for item in PACKAGE_INCLUDE:
            src = os.path.join(SCRIPT_DIR, item)
            if not os.path.exists(src):
                missing.append(item)
                continue
            if os.path.isfile(src):
                zf.write(src, f"ShaoyuLM/{item}")
                added += 1
                log(f"  + {item}")
            elif os.path.isdir(src):
                count = 0
                for root, dirs, files in os.walk(src):
                    dirs[:] = [d for d in dirs if d not in EXCLUDE_PARTS]
                    for f in files:
                        fp = os.path.join(root, f)
                        rel = os.path.relpath(fp, SCRIPT_DIR)
                        if _should_exclude(rel):
                            continue
                        zf.write(fp, f"ShaoyuLM/{rel.replace(os.sep, '/')}")
                        count += 1
                added += count
                log(f"  + {item}/  ({count} 个文件)")

        # 2. 模型
        for m in models:
            mp = os.path.join(MODELS_DIR, m)
            if os.path.isfile(mp):
                size_mb = os.path.getsize(mp) / 1024 / 1024
                zf.write(mp, f"ShaoyuLM/models/{m}")
                added += 1
                log(f"  + models/{m}  ({size_mb:.1f}MB)")
            else:
                missing.append(f"models/{m}")
                log(f"  ! models/{m}  不存在，跳过")

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    log(f"完成: {output}  ({size_mb:.1f}MB, {added} 项)")
    if missing:
        log("缺失:")
        for m in missing:
            log(f"  - {m}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="打包 ShaoyuLM")
    parser.add_argument("--output", default="ShaoyuLM.zip")
    parser.add_argument("--lite", action="store_true",
                        help="精简版：只含 q4_k_m")
    parser.add_argument("--no-models", action="store_true",
                        help="不含模型")
    args = parser.parse_args()

    if args.no_models:
        mode = "none"
    elif args.lite:
        mode = "lite"
    else:
        mode = "full"

    package(args.output, mode=mode)


if __name__ == "__main__":
    main()
