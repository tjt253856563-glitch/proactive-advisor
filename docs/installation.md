# 安装、验证和卸载

当前支持目标是 **Codex 的项目级 Skill 目录**。复制和卸载脚本使用 Python 3.10+ 标准库，Windows / macOS / Linux 使用相同命令。当前本机验证了 Windows 的复制、校验、冲突保护和卸载；目标客户端能否发现、加载以及自动触发，仍需各自验证。

## 安装

先下载或克隆仓库，在仓库根目录运行：

```sh
git clone https://github.com/tjt253856563-glitch/proactive-advisor.git
cd proactive-advisor
python scripts/install.py install --project "你的项目绝对路径"
```

项目目录必须已存在。脚本复制到 `<项目>/.agents/skills/proactive-advisor/`，核对文件 SHA-256 并写入安装收据。已存在的目录一律拒绝覆盖，路径含符号链接或 Windows junction 也拒绝自动操作。不需要 API key，不改客户端全局配置。

也可以手工复制整个 `skills/proactive-advisor` 目录到上述位置；手工安装没有脚本收据，卸载需自己检查文件。

## 在客户端确认

打开目标项目的新会话，输入：

> 使用 $proactive-advisor。请读取项目中的 `.agents/skills/proactive-advisor/SKILL.md`，然后完成我的具体任务：……

检查客户端展示的文件读取或工具轨迹，确认读取的是该文件；然后检查真实输出和修改。**目录存在、界面出现名称或助手自述“已使用”都不能单独证明规则已落实。** 本项目没有声称验证了所有客户端或所有自动触发路径。

项目级路径参考 [官方 Skills 文档](https://learn.chatgpt.com/docs/build-skills)。这不是 ChatGPT Work 的安装指令，也不代表 Work 自动共享本地安装。

## 卸载和升级

在保留的仓库根目录执行：

```sh
python scripts/install.py uninstall --project "你的项目绝对路径"
```

脚本只删除自己安装且所有文件保持原样的 Skill 目录；不删除项目目录或 `.agents/skills` 下的其他内容。发现用户修改、新增文件、缺少收据或链接时会拒绝卸载。请先备份和人工检查这些文件，不要为绕过保护直接删除收据。

升级时先按上述步骤卸载，再安装新版；有个人修改的版本先自行合并，脚本不提供强制覆盖。

## English quick start

From a cloned repository, run `python scripts/install.py install --project "/absolute/project/path"` with Python 3.10+. The project must already exist. The installer copies the skill into `.agents/skills/proactive-advisor`, checks hashes and records a receipt. Existing destinations and symlink/junction paths are refused.

Start a new Codex chat in that project and explicitly request `$proactive-advisor`. Inspect the actual file-read trace and task artifacts; a file copy is not proof of discovery or behavioral improvement. ChatGPT Work installation and automatic triggering have not been validated.

Run `python scripts/install.py uninstall --project "/absolute/project/path"` to remove an unchanged installation. Modified or added files are preserved by refusing removal. Back up and inspect them manually before upgrading.
