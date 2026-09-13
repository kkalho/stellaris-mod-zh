"""单波合并 + 门禁 + 导入 + 重标 一键。用法: python scripts/_merge_import_wave.py 005"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DW = BASE / "translations" / "expand_wave"


def main(wave: str) -> int:
    parts = []
    for name in ("partA", "partB", "partC"):
        p = DW / f"expand_task_{wave}_{name}.json"
        if not p.exists():
            print(f"MISSING {p.name}")
            return 1
        raw = p.read_text(encoding="utf-8")
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            d = json.loads(raw, strict=False)
        rows = d.get("translations") or []
        print(name, len(rows))
        parts.extend(rows)
    seen = set()
    merged = []
    for r in parts:
        sid = str(r.get("steam_id") or "")
        if sid and sid not in seen:
            seen.add(sid)
            merged.append(r)
    # 打扫禁词兜底
    ban = {
        "最强": "突出",
        "顶级": "突出",
        "第一": "先",
        "唯一": "仅有的",
        "史诗级": "大型",
        "必装": "常用",
        "好评": "推荐",
    }
    for r in merged:
        for k in ("title_zh", "summary_zh", "description_zh", "gameplay_zh", "reviews_zh"):
            t = r.get(k) or ""
            for w, rep in ban.items():
                if w in t:
                    t = t.replace(w, rep)
            r[k] = t
        feats = r.get("features_zh")
        if isinstance(feats, list):
            r["features_zh"] = [
                re.sub("最强|顶级|第一|唯一|史诗级|好评", "突出", str(x)) for x in feats
            ]
    out = DW / f"expand_task_{wave}_merged.json"
    out.write_text(
        json.dumps(
            {"game": "stellaris", "source": f"expand wave{int(wave)} merged", "translations": merged},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print("merged", len(merged))
    # 再门禁一次
    g = subprocess.run(
        [sys.executable, str(BASE / "scripts" / "validate_translations.py"), str(out)],
        cwd=str(BASE),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    print(g.stdout)
    if g.returncode != 0:
        print(g.stderr)
        print("GATE_FAIL")
        return 2
    imp = subprocess.run(
        [sys.executable, str(BASE / "scripts" / "import_stellaris_translations.py"), str(out)],
        cwd=str(BASE),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    print(imp.stdout)
    print(imp.stderr)
    if imp.returncode != 0:
        print("IMPORT_FAIL")
        return 3
    for cmd in (
        ["scripts/rebuild_pinyin_idx.py"],
        ["scripts/detect_stellaris_versions.py"],
        ["scripts/detect_stellaris_dlcs.py"],
    ):
        subprocess.run([sys.executable, *cmd], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8")
    v = subprocess.run(
        [sys.executable, str(BASE / "scripts" / "verify_db.py")],
        cwd=str(BASE),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    print((v.stdout or "")[-500:])
    print("WAVE", wave, "DONE exit", v.returncode)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "005"))
