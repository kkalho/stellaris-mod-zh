# 一次性资产生成：web/og_card.png（分享卡片 1200x630）
# 用 py -3.14 运行（3.15 的 Pillow 不兼容）。产物入库后本脚本可删。
from PIL import Image, ImageDraw, ImageFont
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PNG = os.path.join(BASE, "web", "og_card.png")
FONT_DIR = os.path.join("C:" + os.sep, "Windows", "Fonts")

W, H = 1200, 630
img = Image.new("RGB", (W, H), (10, 14, 26))
d = ImageDraw.Draw(img)

# 顶部到下部的深蓝渐变
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)], fill=(int(10 + 8 * t), int(14 + 10 * t), int(26 + 24 * t)))

# 星野：确定性 LCG 伪随机（纯装饰，非加密用途）
state = 42

def nxt():
    global state
    state = (state * 1103515245 + 12345) % 2147483648
    return state

for _ in range(240):
    x = nxt() % W
    y = nxt() % H
    s = (1, 1, 1, 2)[nxt() % 4]
    c = ((90, 110, 150), (140, 170, 210), (95, 215, 255), (216, 226, 240))[nxt() % 4]
    if nxt() % 8 == 0:
        c = (95, 215, 255)
    d.ellipse((x, y, x + s, y + s), fill=c)

# 一条青色「航线」弧线点缀
for i in range(140):
    t = i / 140
    x = int(80 + 700 * t)
    y = int(500 - 120 * t + 26 * (t * t))
    d.ellipse((x, y, x + 2, y + 2), fill=(95, 215, 255))

def font(size, bold=False):
    name = os.path.join(FONT_DIR, "msyhbd.ttc" if bold else "msyh.ttc")
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.truetype(os.path.join(FONT_DIR, "msyh.ttc"), size)

d.text((80, 150), "群星 MOD 中文知识库", font=font(88, bold=True), fill=(226, 236, 250))
d.text((84, 280), "STELLARIS WORKSHOP · 800+ MOD 中文档案", font=font(34), fill=(95, 215, 255))
d.text((84, 340), "汉化包索引 · 兼容冲突检测 · 遗珠榜 · 版本适配标注", font=font(24), fill=(150, 165, 195))

d.line([(80, 60), (200, 60)], fill=(95, 215, 255), width=3)
d.line([(80, 60), (80, 110)], fill=(95, 215, 255), width=3)
d.text((220, 66), "MOD ZH ARCHIVE", font=font(24), fill=(120, 140, 175))

d.line([(W - 80, H - 60), (W - 200, H - 60)], fill=(95, 215, 255), width=3)
d.line([(W - 80, H - 60), (W - 80, H - 110)], fill=(95, 215, 255), width=3)

img.save(OUT_PNG, optimize=True)
print("og_card.png", img.size)
