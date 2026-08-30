"""⛔ 已停用：旧版重建流水线（面向旧版单游戏库 data/stellaris_mods.db，坑 #10）

现役多游戏架构的重建/数据修复请用: python scripts/rebuild_all.py
（收敛式流水线：增量导入 + 重跑标注，不丢 version/DLC/翻译字段）

本脚本曾是「build_db 全量重建 + 旧版导入翻译」的触发链——历史上两次
「version/DLC 标注归零」事故（坑 #1）均由它引起。旧库已被多游戏架构取代，
该流程无现役用途，故硬停用；需要历史实现请查 git 记录。
"""
import sys


def main():
    print("⛔ 本脚本已停用：它面向旧版单游戏库 data/stellaris_mods.db（坑 #10），")
    print("   经 build_db 全量重建 + 旧版导入翻译，是「标注归零」事故的触发链（坑 #1）。")
    print()
    print("   ✅ 现役重建/数据修复请用:  python scripts/rebuild_all.py")
    print("   ✅ 增量扩容导入请用:      python scripts/import_new_batch.py <起> <止>")
    print("   ✅ 数据体检请用:          python scripts/verify_db.py")
    sys.exit(1)


if __name__ == "__main__":
    main()
