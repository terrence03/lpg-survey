"""題目改版時用：把舊版 questions.toml 的題目文字同步進 public/questions.json。

用法：python scripts/toml_to_json.py path/to/questions.toml
只更新題號、題目、選項與答案；跳題規則與分步設定保留在 questions.json 裡手動維護。
"""

import json
import sys
import tomllib
from pathlib import Path

target = Path(__file__).resolve().parent.parent / "public" / "questions.json"
src = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
cfg = json.loads(target.read_text(encoding="utf-8"))
for key, q in src.items():
    d = cfg["questions"].setdefault(key, {"type": "single"})
    for field in ("no", "question", "other_question", "answer", "options"):
        if field in q:
            d[field] = q[field]
target.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"updated {target}")
