# 香港求职追踪 · GitHub 独立版

公开岗位网页 + 固定规则 Python 采集 + GitHub Actions 定时更新。无需 Google、ChatGPT、OpenAI API 或模型 token。

## 功能

- 雇主清单 / 外部发现 / 已读岗位，每类含日常实习 / 暑期实习 / 毕业项目。
- 公司、职位、发布日期、截止日期、原始链接与已读按钮；未知日期不推算。
- 已读状态只保存在当前浏览器，可导出/合并导入。跨设备不自动同步；清理浏览器前请备份。个人已读 JSON 不得提交到公开仓库。
- 97 家雇主，Workopia 香港清单、JobSpy（Indeed / LinkedIn），沿用固定筛选。公开内容不含简历、私人已读状态和账户凭据。
- 每周六香港时间 09:00 更新。网页显示实际更新时间与来源错误；超过 9 天未更新会提示。

## 部署

1. 将本目录作为单独的 GitHub 仓库（`main` 分支），不要上传上级工作目录或迁移备份。
2. 在 Settings → Pages → Build and deployment 中选择 GitHub Actions。
3. 首次 push 会测试并发布现有快照。Actions 中的 `Update jobs and publish` 可手动执行，`refresh` 控制是否重新抓取。
4. 先确认 Pages 部署成功、公开链接可访问，再运行一次 `refresh=true` 验证 GitHub 执行环境的来源可达性。
5. 新站和更新验证通过后才停用旧站定时任务；不要提前删除旧数据。

GitHub Free 的 Pages 通常使用公开仓库；仓库与网页均会公开。不要存任何密钥。工作流只使用仓库内置的短期 GITHUB_TOKEN。计划任务可能延迟或被丢弃；公开仓库 60 天无活动会暂停计划任务，应检查 Actions 和页面更新时间。首次真实定时运行不等于配置文件已验证。

## 本地使用和验证

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
node --test core.test.cjs
.venv/bin/python build.py
```

生成的 `dist/index.html` 可以在浏览器打开，需保留整个 `dist` 目录。若浏览器限制本地文件存储，运行 `python3 -m http.server 8080 --directory dist` 后访问本机页面。离线版本不会自动获取后续更新，应重新下载构建文件或使用线上链接。

手动更新：`.venv/bin/python update.py`，然后重新构建。数据以稳定岗位 ID 合并；缺失或抓取失败不删除旧岗位；只有明确截止日期才用于隐藏过期未读岗位。全部来源失败时保留原文件并返回失败状态。

## 采集边界

官网采用公开接口、结构化数据、有限链接检查；不覆盖所有岗位。不绕过 robots.txt、登录、验证码或访问限制。外部来源只是发现线索，不是资格或岗位仍开放的证明。申请前请核对原始招聘页。2027 届毕业项目需自行核对毕业与入职要求。

雇主池来自 2026-09-11 本地工作簿中的 96 家公司及后来补入的 LVMH；没有从不可用的 Google Drive 读取最新版。

来源：[Workopia](https://github.com/workopia/Hong-Kong-Graduate-Internship-Jobs)、[JobSpy](https://github.com/speedyapply/JobSpy)。
