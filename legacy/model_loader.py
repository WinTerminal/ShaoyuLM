# model_loader.py - load shaoyu model
import os
import torch
from transformers import AutoTokenizer
from model_minimind import MiniMindForCausalLM, MiniMindConfig

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
DTYPE = torch.float32 if DEVICE == 'cpu' else torch.bfloat16
if DEVICE == 'cpu':
    torch.set_num_threads(8)

print(f"device: {DEVICE} | dtype: {DTYPE}")

tokenizer = AutoTokenizer.from_pretrained(
    os.path.join(SCRIPT_DIR, "tokenizer")
)

config = MiniMindConfig(
    hidden_size=512,
    num_hidden_layers=10,
    intermediate_size=1408,
    num_key_value_heads=2,
    use_moe=False,
    max_position_embeddings=32768,
)

model = MiniMindForCausalLM(config)
state = torch.load(
    os.path.join(SCRIPT_DIR, "full_sft_512.pth"),
    map_location='cpu',
    weights_only=True,
)
model.load_state_dict(state, strict=False)
model = model.to(DEVICE).to(DTYPE).eval()

print("shaoyu model loaded\n")
