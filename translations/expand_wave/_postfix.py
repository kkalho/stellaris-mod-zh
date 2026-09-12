import json

p = r'C:\Users\wangf\Desktop\群星工具\stellaris-mod-zh\.worktrees\expand-2000\translations\expand_wave\expand_task_002_partB.json'
with open(p, encoding='utf-8') as f:
    data = json.load(f)

# Fix minor issues found in validation
for t in data['translations']:
    if t['steam_id'] == '2911033004':
        t['description_zh'] = t['description_zh'].replace(
            '欢迎回家，指挥官——本模组将玩家带入质量效应熟悉的物种指挥中心，在一个没有薛帕德救场的宇宙中改写银河史。',
            '欢迎回家，指挥官——本模组带你进入质量效应熟悉的物种指挥中心，在一个没有薛帕德救场的宇宙中改写银河史。'
        ).replace(
            '约 600 个手工放置系统，组织成约 155 个星团',
            '约 600 个手工系统，组织成约 155 个星团'
        ).replace(
            '行星多样性、Guilli、Real Space New Frontiers 等不兼容。',
            '行星多样性、Guilli、Real Space New Frontiers 不兼容。'
        )
    # remove zero-width / invisible chars
    for k in ['title_zh','summary_zh','description_zh','gameplay_zh','reviews_zh']:
        t[k] = (
            t[k]
            .replace('​', '')
            .replace('﻿', '')
            .replace('‌', '')
            .replace('‍', '')
            .replace(' ', ' ')
        )
    # fix awkward Unlicense phrasing if any
    t['description_zh'] = t['description_zh'].replace('Unlicense（无license协议）', 'Unlicense（无许可协议）')

# strip invisible chars from features too
for t in data['translations']:
    t['features_zh'] = [
        x.replace('​','').replace('﻿','').replace(' ',' ').strip()
        for x in t['features_zh']
    ]

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
