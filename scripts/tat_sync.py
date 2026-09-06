"""通过 TAT 自动化助手把云同步脚本推送到腾讯云并执行。

用法: python scripts/tat_sync.py --script <同步脚本.sh> [--poll-inv INV_ID]
--script 必填（一次性脚本已按 §14.1.5 清理，无默认值）；脚本通常由 run_wave.py sync 生成。
"""
import sys, base64, json, os, time
from pathlib import Path

from tccli.main import main

REGION = "ap-shanghai"
INSTANCE = "lhins-ca3ol8ju"


def run_command(script):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = Path(here).resolve()
    sh_path = (root / script).resolve()
    if not sh_path.is_relative_to(root):
        raise SystemExit(f"拒绝越界路径: {script}")
    content = sh_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    b64 = base64.b64encode(content).decode()
    args = [
        "tccli", "tat", "RunCommand",
        "--region", REGION,
        "--Content", b64,
        "--InstanceIds", '["%s"]' % INSTANCE,
        "--CommandType", "SHELL",
        "--Timeout", "300",
    ]
    sys.argv = args
    return main()


def describe(inv_id):
    args = [
        "tccli", "tat", "DescribeInvocationTasks",
        "--region", REGION,
        "--Filters", '[{"Name":"invocation-id","Values":["%s"]}]' % inv_id,
        "--HideOutput", "false",
    ]
    sys.argv = args
    return main()


if __name__ == "__main__":
    if "--poll-inv" in sys.argv:
        inv_id = sys.argv[sys.argv.index("--poll-inv") + 1]
        sys.exit(describe(inv_id))
    if "--script" in sys.argv:
        script = sys.argv[sys.argv.index("--script") + 1]
    else:
        raise SystemExit("用法: python scripts/tat_sync.py --script <同步脚本.sh> [--poll-inv INV_ID]")
    sys.exit(run_command(script))
