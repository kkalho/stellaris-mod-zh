import json

p = r'C:\Users\wangf\Desktop\群星工具\stellaris-mod-zh\.worktrees\expand-2000\translations\expand_wave\expand_task_002_partB.json'
with open(p, encoding='utf-8') as f:
    data = json.load(f)

for t in data['translations']:
    if t['steam_id'] == '2726458423':
        t['gameplay_zh'] = (
            "• 订阅并启用本体「舰队collection：镇守府星际大冒险」后，再启用本语音包即可听到时雨配音。\n"
            "• 由于语音已独立成包，未来更新或新增其他角色语音时不必重装整个本体。\n"
            "• 若你只想要部分语音，需以本体实际结构为准；本页说明未提供单独角色开关细节。\n"
            "• 安装后进入游戏，在本体提供语音的场合触发相应语音即可验证是否生效。\n"
            "• 若与本体旧版内嵌语音重复，优先保留独立语音包并去除重复内容。\n"
            "• 适合用作本体游玩时的氛围增强；若主要玩原版群星则无需订阅。\n"
            "• 可关注作者后续更新，逐步补齐更多角色语音后获得更完整体验。\n"
            "• 若语音未播放，先确认本体版本与加载顺序，再检查是否误关了音效设置。\n"
            "• 当前可把它当作时雨专属语音插件，不必预期覆盖全部角色台词。"
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
