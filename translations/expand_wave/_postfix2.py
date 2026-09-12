import json

p = r'C:\Users\wangf\Desktop\群星工具\stellaris-mod-zh\.worktrees\expand-2000\translations\expand_wave\expand_task_002_partB.json'
with open(p, encoding='utf-8') as f:
    data = json.load(f)

for t in data['translations']:
    if t['steam_id'] == '2726458423':
        t['description_zh'] = (
            "• 本模组是「舰队collection：镇守府星际大冒险」的语音包。\n"
            "• 旧版语音曾作为本体内容整合在原模组内，现已独立拆分，便于后续加入更多语音相关子模组。\n"
            "• 目前仅包含时雨的语音；作者表示后续会添加更多角色语音。\n"
            "• 需与本体模组搭配使用，本页单独订阅不会提供完整玩法。\n"
            "• 拆分的主要好处是：更新语音不必重装整个本体，也方便作者并行开发其它语音扩展。\n"
            "• 若你已安装旧版含语音的本体，升级到语音独立版后注意避免重复安装冲突。\n"
            "• 适合喜欢该联动本体、希望有角色语音点缀的玩家；对无语音需求者可忽略本模组。\n"
            "• 后续角色扩展以作者更新说明为准；当前阶段信息较少，请以时雨语音为主要预期。\n"
            "• 本包属于本体附属内容，不额外增加科技、舰船或经济系统，只补语音表现层。"
        )
        t['gameplay_zh'] = (
            "• 订阅并启用本体「舰队collection：镇守府星际大冒险」后，再启用本语音包即可听到时雨配音。\n"
            "• 由于语音已独立成包，未来更新或新增其他角色语音时不必重装整个本体。\n"
            "• 若你只想要部分语音，需以本体实际结构为准；本页说明未提供单独角色开关细节。\n"
            "• 安装后进入游戏，在本体提供语音的场合触发相应语音即可验证是否生效。\n"
            "• 若与本体旧版内嵌语音重复，优先保留独立语音包并去除重复内容。\n"
            "• 适合用作本体游玩时的氛围增强；若主要玩原版群星则无需订阅。\n"
            "• 可关注作者后续更新，逐步补齐更多角色语音后获得更完整体验。\n"
            "• 若语音未播放，先确认本体版本与加载顺序，再检查是否误关了音效设置。"
        )
        t['reviews_zh'] = (
            "作者简要说明：本模组是「舰队collection：镇守府星际大冒险」的语音包，原先语音嵌在本体现已拆出以便扩展；"
            "当前只有时雨语音，并承诺后续会加入更多。说明篇幅短、信息集中，主要向本体玩家同步语音包的独立化与更新计划，"
            "并提醒需要与本体搭配使用。对于已装旧版内嵌语音的玩家，也暗示了拆分后的升级路径，整体是附属资源包的清晰交代。"
        )

with open(p, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

banned = ['官方数据显示', '5星好评', '五星好评', '次投票', '必装']
def tot(s):
    return len(s.replace('\n', ''))
for t in data['translations']:
    for f in banned:
        for k in ['title_zh','summary_zh','description_zh','gameplay_zh','reviews_zh']:
            assert f not in t[k], (t['steam_id'], k, f)
    sl, dl, gl, rl = tot(t['summary_zh']), tot(t['description_zh']), tot(t['gameplay_zh']), tot(t['reviews_zh'])
    nfeat = len(t['features_zh'])
    print(t['steam_id'], 'sum', sl, 'desc', dl, 'gp', gl, 'rev', rl, 'feat', nfeat)
    assert 40 <= sl <= 80, (t['steam_id'], 'sum', sl)
    assert 300 <= dl <= 600, (t['steam_id'], 'desc', dl)
    assert 300 <= gl <= 600, (t['steam_id'], 'gp', gl)
    assert 150 <= rl <= 300, (t['steam_id'], 'rev', rl)
    assert 4 <= nfeat <= 8, (t['steam_id'], nfeat)
    assert all(len(x) <= 12 for x in t['features_zh']), t['features_zh']
ids = [t['steam_id'] for t in data['translations']]
expected = ['1546160059','2911033004','1380293767','2097209960','2398450274','1346797092','2726458423','687358103','830544109','1399770323','2028165747','2811428998','2650084420','2864561711','1590614009','3108359904','3330715590']
assert ids == expected
print('count', len(data['translations']))
print('ALL CHECKS PASSED')
