"""Modelleri sırayla çalıştırır; GPU başka bir işle (ör. oyun) meşgulken bekler."""
from __future__ import annotations

import statistics
import subprocess
import sys
import time

from .run import gpu_state

MODELS = [  # (model, gereken boş VRAM MiB)
    ("llama3.2:3b", 3500),
    ("gemma3:4b", 5000),
    ("qwen3:8b", 7000),
    ("tohum-8b:latest", 7000),
    ("qwen3:14b", 10500),
    ("tohum-14b-v2:latest", 10500),
]


def wait_idle(need: int) -> None:
    while True:
        samples = []
        for _ in range(5):
            samples.append(gpu_state())
            time.sleep(2)
        free = min(s[0] for s in samples)
        util = statistics.mean(s[1] for s in samples)
        if free >= need and util < 40:
            return
        print(f"GPU meşgul (boş {free} MiB, kullanım %{util:.0f}); 2 dk sonra tekrar bakılacak", flush=True)
        time.sleep(120)


def main() -> None:
    models = MODELS if len(sys.argv) < 2 else [m for m in MODELS if m[0] in sys.argv[1:]]
    for i, (m, need) in enumerate(models):
        if i:  # önceki modeli VRAM'den boşalt
            subprocess.run(["ollama", "stop", models[i - 1][0]], capture_output=True)
            time.sleep(5)
        wait_idle(need)
        print(f"== {m} başlıyor", flush=True)
        subprocess.run([sys.executable, "-m", "karne.run", m, "--split", "all"], check=True)
    if models:
        subprocess.run(["ollama", "stop", models[-1][0]], capture_output=True)


if __name__ == "__main__":
    main()
