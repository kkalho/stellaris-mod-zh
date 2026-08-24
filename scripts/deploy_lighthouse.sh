#!/bin/bash
# ============================================================
# stellaris-mod-zh 一键部署脚本（腾讯云轻量服务器 / OpenCloudOS 9）
# 用法：
#   1. 把本部署包上传到服务器（网页终端 OrcaTerm 支持上传 tar.gz）
#   2. tar -xzf stellaris-mod-zh-deploy.tar.gz && cd stellaris-mod-zh-deploy
#   3. sudo bash deploy_lighthouse.sh
# 部署后：http://<服务器公网IP>:8080
# ============================================================
set -u
APP_DIR=/opt/stellaris-mod-zh
PORT=8080
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=============================================="
echo " stellaris-mod-zh 部署（1/5）安装依赖"
echo "=============================================="
# python3
if ! command -v python3 >/dev/null 2>&1; then
  echo "  安装 python3 ..."
  sudo dnf install -y python3 2>/dev/null || sudo yum install -y python3 2>/dev/null
fi
PY="$(command -v python3)"
echo "  Python: $($PY --version 2>&1)"
# pip（ensurepip 兜底）
$PY -m ensurepip --upgrade 2>/dev/null || true
# pypinyin（拼音搜索必需）
$PY -m pip install --no-input pypinyin 2>/dev/null || $PY -m pip install pypinyin 2>/dev/null || \
  echo "  ⚠ pypinyin 安装失败（可稍后手动安装）"
# git（若需从 GitHub 更新）
command -v git >/dev/null 2>&1 || sudo dnf install -y git 2>/dev/null || true

echo "=============================================="
echo " 部署（2/5）拷贝代码到 $APP_DIR"
echo "=============================================="
sudo mkdir -p "$APP_DIR"
sudo cp -r "$SRC_DIR"/web_server_multigame.py "$SRC_DIR"/core "$SRC_DIR"/games \
        "$SRC_DIR"/web "$SRC_DIR"/data "$SRC_DIR"/translations "$SRC_DIR"/scripts \
        "$SRC_DIR"/docs "$SRC_DIR"/LICENSE "$SRC_DIR"/README.md "$APP_DIR"/ 2>/dev/null || {
  echo "  复制失败，改为整目录复制"; sudo cp -r "$SRC_DIR"/* "$APP_DIR"/; }
sudo chown -R "$(whoami)" "$APP_DIR" 2>/dev/null || true

echo "=============================================="
echo " 启动（3/5）测试运行"
echo "=============================================="
cd "$APP_DIR"
# 数据库完整性自检
$PY -c "import sqlite3; c=sqlite3.connect('data/stellaris/mods.db'); print('  群星库 MOD 数:', c.execute('select count(*) from mods').fetchone()[0])" 2>&1
$PY -c "import sqlite3; c=sqlite3.connect('data/ck3/mods.db'); print('  CK3 库 MOD 数:', c.execute('select count(*) from mods').fetchone()[0])" 2>&1
# 短启动测试
nohup $PY web_server_multigame.py $PORT --no-browser --host 0.0.0.0 >/tmp/smz_test.log 2>&1 &
sleep 2
curl -s "http://127.0.0.1:$PORT/api/stellaris/stats" >/dev/null && echo "  ✅ 测试启动成功" || { echo "  ❌ 测试启动失败，日志："; tail -5 /tmp/smz_test.log; }
pkill -f "web_server_multigame.py $PORT" 2>/dev/null || true
sleep 1

echo "=============================================="
echo " 常驻（4/5）注册 systemd 服务"
echo "=============================================="
sudo tee /etc/systemd/system/stellaris-mod.service >/dev/null <<EOF
[Unit]
Description=Paradox MOD 查询工具 (stellaris-mod-zh)
After=network.target

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$PY $APP_DIR/web_server_multigame.py $PORT --no-browser --host 0.0.0.0
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable stellaris-mod >/dev/null 2>&1
sudo systemctl restart stellaris-mod
sleep 2
sudo systemctl is-active stellaris-mod >/dev/null && echo "  ✅ systemd 服务运行中" || { echo "  ❌ 服务未启动，查看日志："; sudo journalctl -u stellaris-mod -n 10 --no-pager; }

echo "=============================================="
echo " 防火墙（5/5）放行 $PORT 端口"
echo "=============================================="
# 轻量服务器安全组在控制台放行；此处兜底本机 firewalld
if command -v firewall-cmd >/dev/null 2>&1; then
  sudo firewall-cmd --permanent --add-port=$PORT/tcp >/dev/null 2>&1 || true
  sudo firewall-cmd --reload >/dev/null 2>&1 || true
  echo "  firewalld 已放行 $PORT/tcp"
else
  echo "  未装 firewalld，请确认轻量控制台防火墙已放行 $PORT 端口"
fi

echo ""
echo "=============================================="
echo " ✅ 部署完成！"
echo "    公网访问: http://<服务器公网IP>:$PORT"
echo "    状态:     systemctl status stellaris-mod"
echo "    日志:     journalctl -u stellaris-mod -f"
echo "    更新:     cd $APP_DIR && git pull 或重新上传部署包"
echo "=============================================="
