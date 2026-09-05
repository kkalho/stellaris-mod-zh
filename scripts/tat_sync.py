"""通过 TAT 自动化助手把 cloud_sync_fix.sh 推送到腾讯云并执行。

用法: python scripts/tat_sync.py [--poll-inv INV_ID]
默认动作: 读取 cloud_sync_fix.sh -> base64 -> RunCommand -> 打印 InvocationId。
"""
import sys, base64, json, os, time
from pathlib import Path

from tccli.main import main

REGION = "ap-shanghai"
INSTANCE = "lhins-ca3ol8ju"


def run_command(script="cloud_sync_fix.sh"):
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
    script = "cloud_sync_fix.sh"
    if "--script" in sys.argv:
        script = sys.argv[sys.argv.index("--script") + 1]
    sys.exit(run_command(script))
