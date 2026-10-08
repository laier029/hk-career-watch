# 香港求职追踪 · v2

[打开网站](https://laier029.github.io/hk-career-watch/) · [真实岗位核验与来源限制](AUDIT.md)

GitHub Pages + Python 固定规则 + GitHub Actions。无登录、模型调用、付费 API 或常驻服务器；不依赖 Google / ChatGPT 账号。

## 每次怎么检查

1. 默认打开 **供应链 → 待查看**。新发现、重要变更优先；旧的未处理岗位不会消失。
2. 查看 **待核实**：这里可能有好机会，但毕业窗口、香港地点或项目时间还需确认。它不是“不合适”清单。
3. 日常实习 / 寒暑假实习 / 毕业项目可以快捷筛选；四个供应链方向支持多选。其他商科单独切换。
4. 可已读、收藏、已投递、不合适；操作可撤销，只对选中的岗位批量已读。打开官网不会自动算已投递。
5. 查看完点“本次检查完成”，仅更新新发现标记，不会批量清除未读。

所有筛选在本机完成，不请求外部网站。个人记录仅保存于当前浏览器 / 当前网站地址；定期“导出记录”，换设备后“导入记录”。不要把私人备份提交到公开仓库。旧 v1 已读备份可导入，旧 ID 仅在唯一对应时迁移；歧义与未匹配记录保留。收藏和已投递岗位归档后仍可查看。

## 数据流与更新

97 家重点雇主公开页 / ATS、FreeHire 完整职位搜索、Workopia 香港学生清单、JobSpy Indeed / LinkedIn → 同一规则核对 → 去重 / 历史保留 → 公共静态快照。

- 香港时间每日 **08:15** 轻量更新 FreeHire / Workopia（周六除外）。
- 周六 **09:00** 全面更新四类来源及已知官网链接。
- GitHub → Actions → **Update jobs and publish** → Run workflow：`light` 轻量、`full` 全面、`publish` 仅发布现有数据。
- 主分支代码提交先测试，再发布，不触发重复采集。
- GitHub 计划任务可能延迟；页面在轻量超过 48 小时、全面超过 9 天未成功时提醒。公开仓库长期无活动时也应检查 Actions 是否暂停。

FreeHire 使用公开 `/api/v1/agent/jobs/search`（附完整职位说明），按香港学生项目和供应链职能两条路径分页读取；参数忽略、分页上限和失败会显示为异常。JobSpy 每词每站目标 100 条、近 14 天，达到上限明确报告可能截断。无付费服务，但第三方接口将来可能变化或限流。

重点雇主按企业身份标记，不取决于发现来源。外部发现不会自动扩大 97 家重点雇主池。官网 / ATS 优先展示，同一岗位保留多来源；不因公司和标题相同就合并不同职位编号或年份。

## 规则和维护入口

| 文件 | 负责内容 |
|---|---|
| `config.json` | 97 家企业、别名、官网入口、JobSpy 站点 |
| `rules.json` | 中英文方向词、查询词、排除词、目标年份、30 天复查阈值 |
| `official-watch.json` | 已人工核验的官方具体岗位，及确证同一职位的链接别名 |
| `model.py` | 地点 / 类型 / 职能 / 时间核对，去重与生命周期 |
| `update.py` | 来源适配和采集；新增常规关键词不需改程序 |
| `jobs.json` | 公共快照 v2；不包含个人申请状态 |
| `core.js` / `app.js` | 本地筛选和个人记录 / 页面交互 |
| `acceptance-samples.json` / `audit.py` | 官方岗位对照与离线审计报告 |

只收明确实习、学生 Placement、正式 Graduate Programme / MT；“欢迎应届生”的普通正式岗不纳入。地点以实际岗位为准，不能因公司介绍出现香港而通过。寒假 / 暑假必须有证据，一月入职不自动算寒假。2027 年 11 月毕业与各项目资格窗口逐项核对，未知信息不推算。

明确关闭或截止归档；连续 30 天未被官方重新确认进入待复查。单源失败保留历史；全部来源失败不改快照、Actions 报错并保留诊断。来源刷新发布日期不算新增。截止、入职、资格或申请链接重要变更后，已读记录重新提示，收藏和投递保留。

## 本地验证

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
node --test core.test.cjs
.venv/bin/python build.py
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory dist
```

更新：`.venv/bin/python update.py --profile light` 或 `--profile full`，之后重新构建。离线报告：`.venv/bin/python audit.py`。`audit.py --finalize` 仅用于本次有 `output/watch-snapshot.json` 的迁移补充，不是日常维护命令。

`ui.test.cjs` 是可选的本地 Playwright 回归测试，需自行准备 Playwright 与 Chrome；无需进入日常定时流程。静态发布只包含构建后的网页资产，构建器对公共字段做白名单校验。

## 覆盖边界与回退

官网适配 Workday / Lever / Greenhouse / SmartRecruiters 和公开结构化页面；不绕过登录、验证码、robots 或访问限制。读取到招聘首页不等于查遍所有岗位，来源诊断会标为“部分覆盖”。JobSpy / FreeHire 是发现线索，不是官方仍开放或本人符合资格的证明。

本次用 GitHub 最新快照 `cd89d77ae6bcddb4aa52b410be23c2c0794eb0de` 作为迁移基线（239 条），未用陈旧本地文件覆盖线上。该提交保留旧代码和快照，可在 GitHub 对本次改版提交执行 Revert 后重新发布。回退到旧版前先导出 v2 私人记录；v1 不识别收藏 / 投递，备份可在恢复 v2 后重新导入。

97 家雇主来自原 96 家清单及 LVMH，不能声称覆盖香港全部雇主。样本审计记录发现、排除、待核实和漏项；岗位总数增加不等于召回率提高。申请前仍须打开原岗位确认。

已知第三方公司标注纠错也放在 `rules.json`：Workable 职位 `929B9618D2` 的官方跳转和页面标题为 [Love, Bonito](https://apply.workable.com/lovebonito/j/929B9618D2)，不能沿用 FreeHire 的 Esevel 标注。纠错必须有官方证据，不按猜测扩充。

来源：[FreeHire API](https://freehire.me/docs/api)、[Workopia](https://github.com/workopia/Hong-Kong-Graduate-Internship-Jobs)、[JobSpy](https://github.com/speedyapply/JobSpy)。
