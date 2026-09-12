import json

p = r'C:\Users\wangf\Desktop\群星工具\stellaris-mod-zh\.worktrees\expand-2000\translations\expand_wave\expand_task_002_partB.json'
with open(p, encoding='utf-8') as f:
    data = json.load(f)

by = {t['steam_id']: t for t in data['translations']}

# 2726458423 features short
by['2726458423']['features_zh'] = ["舰队collection", "独立语音包", "时雨配音", "本体附属", "后续扩充"]

# 687358103 expand gameplay
by['687358103']['gameplay_zh'] = (
    "• 对敌方或中立世界进行完全/末日轰炸，将地面防御降至 0。\n"
    "• 在可触发的选项中选择玻璃化或核平，分别得到不可殖民死寂世界或墓土世界。\n"
    "• 适合灭绝流、净化流或「不要了就毁掉」的 RP/战略玩法，避免强行登陆的陆军与时间成本。\n"
    "• 想保留可殖民废土就选核平（墓土）；想彻底断绝对方或自己再殖民就选玻璃化。\n"
    "• 若目标星系有后续通行价值，也可第三项「什么都不做」，仅完成战术轰炸。\n"
    "• 因已停更，建议先在测试档确认事件选项是否仍出现在你的版本中。\n"
    "• 若你喜欢该功能并愿意维护，可 fork 分支并留下链接，让社区继续使用。\n"
    "• 使用时注意区分「战术削弱」与「永久抹除」两种结果的长期战略影响。"
)

# 830544109 shorten summary and description
by['830544109']['summary_zh'] = "让NSC与ISB Doomsday共存的兼容补丁：合并国家类型、用科技梯解锁ISB终局舰；作者已停更于1.9时代。"
by['830544109']['description_zh'] = (
    "• 作者声明：电脑损坏且个人生活进入重要转折，进入 2.0 后不再维护任何模组，全部停留在 1.9 状态；若有人愿意接手可自行维护，但须在更新说明中致谢原作者。\n"
    "• 术语：NSC = New Ship Classes（本补丁针对 Main 或 Streamlined 其一）；ISB = Improved Ship Battles，本补丁仅适配 Doomsday 版。\n"
    "• 使用前提：必须按规则组合右侧所列模组——只能启用其一的 NSC 主体/精简版；必须是 ISB Doomsday（若你用的是 ISB Balance，请改用另一份 Balance 补丁）。\n"
    "• 功能一：合并双方 country_types，使 AI 能同时使用 NSC 舰级与 ISB 舰级，避免互相覆盖只剩一方可用。\n"
    "• 功能二：通过科技要求平衡强度——多数 ISB 终局舰（泰坦、利维坦、厄瑞玻斯、化身）需先研究 NSC 超级无畏科技才能解锁，保证先体验 NSC 各舰级，再在游戏后期拿到更强的 ISB 舰。\n"
    "• 例外：ISB 诸神黄昏（Ragnarok）对应 NSC 旗舰，仅在研究 NSC 旗舰科技后解锁，且同样只可建造一艘。\n"
    "• 解锁顺序概括：NSC 无畏 → NSC 超级无畏 → 除诸神黄昏外的 ISB 舰可用 → NSC 旗舰 → ISB 诸神黄昏。\n"
    "• 因作者已停更于 1.9，现代版本基本不可直接使用；仅作怀旧/旧档参考，移植需自行消化。"
)

# 1399770323 expand gameplay slightly
by['1399770323']['gameplay_zh'] = (
    "• 若你想给建筑换上更易区分的图标，又担心改事件建筑导致成就被禁，选用本成就友好版即可。\n"
    "• 已装完整 EUTAB 的玩家跳过本模块，避免重复叠加。\n"
    "• 因不碰事件建筑文件、号称零性能负担，可作为长期常驻的轻量视觉模组。\n"
    "• 安装后浏览行星建筑界面，确认常见建筑图标是否已区分；事件特殊建筑可能仍用原图。\n"
    "• 想要更完整的独特科技/建筑体验，再去看 Ethos Unique Techs and Buildings。\n"
    "• 不涉及新机制或数值改动，纯粹是图标层面的清晰度提升，适合全类型玩家。\n"
    "• 若与其它大规模 UI 重绘模组同开，把本模块放在较后位置以便图标替换生效。\n"
    "• 成就向玩家尤其适合：图标更清晰的同时不影响成就解锁条件。"
)

# 2028165747 expand gameplay
by['2028165747']['gameplay_zh'] = (
    "• 创建帝国时可选用 Hierarchy 旗帜、城市组与舰船组，获得外星 UFO 风味的舰队外观。\n"
    "• 想要更完整阵营玩法（预设帝国/陆军/起始系）请另装其依赖中的补丁。\n"
    "• 使用 NSC 时按说明配合；若船体显示过大，叠加 Downscaled Ships 补丁。\n"
    "• 可与 Novus、Masari、肖像模组一起搭建多阵营对局，还原宇宙大战阵营对抗。\n"
    "• 本模组以外观资产为主，不替代原版战斗数值体系，胜负仍取决于你的运营与配装。\n"
    "• 建议在创建帝国界面先确认旗帜与城市组是否出现，再进入游戏检查舰船模型。\n"
    "• 若与其它舰船重绘模组冲突，调整加载顺序使 Hierarchy 舰船组优先。\n"
    "• 适合想要快速获得「外星 UFO 舰队」观感、而不改动科技经济的玩家。"
)

# 2650084420 expand gp and reviews, fix features
by['2650084420']['gameplay_zh'] = (
    "• 在与作者所述兼容区间接近的版本上使用，或自行测试 3.8 表现。\n"
    "• 打开方式：政府法令界面寻找对应法令，或使用控制台事件 csm.1122。\n"
    "• 若法令列表缺失，检查是否手动安装到正确 workshop 目录。\n"
    "• 打开菜单后按界面选项调整所需资源或效果；具体条目以游戏内为准。\n"
    "• 属于测试/沙盒向工具，可能影响成就与平衡，按需启用。\n"
    "• 若与其它 UI/脚本模组冲突，优先保证作弊菜单加载顺序清晰并单独存档测试。\n"
    "• 不建议在追求成就或联机的存档中长期挂载；本地沙盒与开发测试更合适。\n"
    "• 控制台事件 csm.1122 通常比找法令更直接，适合熟悉控制台的玩家。"
)
by['2650084420']['reviews_zh'] = (
    "作者实话实说：最适合的兼容版本是 3.3–3.4，3.8 并未做全面测试；并给出两种打开方式与手动安装路径提示。"
    "项目采用 Unlicense，部分实现学习自 BetterCheats 并公开致谢。说明简短、信息实用，没有夸大功能，"
    "属于典型个人小工具的坦率文档，提醒用户自行评估版本风险，适合本地测试与沙盒场景。"
)
by['2650084420']['features_zh'] = ["作弊菜单", "法令控制台", "3.3-3.4推荐", "手动安装", "Unlicense", "致谢BetterCheats"]

# 2864561711 expand gameplay by 1 char - already 299, add one word
by['2864561711']['gameplay_zh'] = by['2864561711']['gameplay_zh'].replace(
    "若你同时使用大量数值 mod",
    "若你同时使用大量数值类 mod"
)

# 1590614009 expand gameplay
by['1590614009']['gameplay_zh'] = (
    "• 将本模组放在列表顶部启用，观察帧率是否改善、画面可接受度如何。\n"
    "• 若画面仍卡，再搭配同系列主性能模组与尘埃精简；替换贴图类模组记得放本模组下方。\n"
    "• 不希望界面糊：确保 UI 模组在本模组之后加载。\n"
    "• 不希望角色肖像或船体主色糊：本模组已豁免肖像与漫反射，但法线/高光仍简化，远观细节会下降。\n"
    "• 使用低画质时效果叠加更明显，适合低配机器极限求帧，不适合截图党。\n"
    "• 4.3.3 已适配；若升级大版本，先验证是否仍生效再保留。\n"
    "• 可先只开本模组跑一次基准，再逐步叠加其它性能 mod，观察哪一项收益最大。\n"
    "• 若某些战役特效异常变糊，优先检查是否与其它贴图优化模组叠用。"
)

# 3330715590 expand desc and gameplay
by['3330715590']['description_zh'] = (
    "• 已更新至 v4.4.*，兼容 Stellaris v4.4 或更高版本；旧版本另有独立条目。\n"
    "• 简单、可配置的自动建造器。\n"
    "• 现已支持自动建造：星港（Starbases）、采矿站/研究站、超空间中继站（Hyperspace Relays）。\n"
    "• 启用方式：进入法令界面，选择「打开扩张管理报告」以启用配置事件。\n"
    "• 支持语言：简体中文、英文（机器翻译）。\n"
    "• 定位是减少中后期点选微操的实用小工具，不宣称重做帝国建造系统。\n"
    "• 因语言为中英双语（英文机翻），界面文本以中文说明与游戏内表现为准。\n"
    "• 若你的模组列表已有其它自动建造类工具，请避免功能重叠导致重复下单或冲突。\n"
    "• 旧版用户若升级到 4.4+，请改订本条目以保证脚本与事件匹配当前游戏版本。"
)
by['3330715590']['gameplay_zh'] = (
    "• 更新游戏至 4.4+，订阅并启用本模组。\n"
    "• 在法令界面点「打开扩张管理报告」，按配置事件设定自动建造规则。\n"
    "• 开启后可让星港、资源/研究站与超空间中继站按你的设定自动完成，减少中后期点选微操。\n"
    "• 适合多线扩张、懒得手动铺站的玩家；若你的列表里已有其他自动建造模组，请注意避免功能重叠。\n"
    "• 英文为机器翻译，以中文说明与游戏内中文选项为准；遇到文本怪异可对照原条目。\n"
    "• 建议先在单机测试档验证触发与建造结果，再用于主力存档。\n"
    "• 若某类建筑你希望手动精控，可在配置中收窄自动范围，只让星港或中继站自动。\n"
    "• 自动建造只减少点击，不改变建筑收益，因此不涉及额外平衡调整。"
)

with open(p, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

banned = ['官方数据显示', '5星好评', '五星好评', '次投票', '必装']
def tot(s):
    return len(s.replace('\n', ''))
issues = []
for t in data['translations']:
    for f in banned:
        for k in ['title_zh','summary_zh','description_zh','gameplay_zh','reviews_zh']:
            if f in t[k]:
                issues.append((t['steam_id'], k, 'banned', f))
    sl, dl, gl, rl = tot(t['summary_zh']), tot(t['description_zh']), tot(t['gameplay_zh']), tot(t['reviews_zh'])
    nfeat = len(t['features_zh'])
    print(t['steam_id'], 'sum', sl, 'desc', dl, 'gp', gl, 'rev', rl, 'feat', nfeat)
    if not (40 <= sl <= 80): issues.append((t['steam_id'], 'sum', sl))
    if not (300 <= dl <= 600): issues.append((t['steam_id'], 'desc', dl))
    if not (300 <= gl <= 600): issues.append((t['steam_id'], 'gp', gl))
    if not (150 <= rl <= 300): issues.append((t['steam_id'], 'rev', rl))
    if not (4 <= nfeat <= 8): issues.append((t['steam_id'], 'feat', nfeat))
    if any(len(x) > 12 for x in t['features_zh']): issues.append((t['steam_id'], 'feat_long', t['features_zh']))
ids = [t['steam_id'] for t in data['translations']]
expected = ['1546160059','2911033004','1380293767','2097209960','2398450274','1346797092','2726458423','687358103','830544109','1399770323','2028165747','2811428998','2650084420','2864561711','1590614009','3108359904','3330715590']
if ids != expected: issues.append(('ids', ids))
print('ISSUES:', issues if issues else 'NONE')
print('count', len(data['translations']))
