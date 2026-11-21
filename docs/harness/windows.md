# Windows 安装、演示与卸载

需要 Python 3.10 或以上。Harness 使用 Python 标准库。基础演示无需下载模型、安装 Python 第三方包或购买服务。

## 安装

从开发分支或 PR 下载源码后，在 PowerShell 进入仓库根目录。可以从源码直接运行，也可以安装一份到当前用户的目录。

```powershell
py -3 --version
$Install = Join-Path $env:LOCALAPPDATA "ProactiveAdvisor\2.0"
py -3 -B .\scripts\install_harness.py install --destination $Install
Set-Location $Install
```

安装器会核对目标是否已存在。它不配置开机启动、注册表或全局 PATH。使用 `-B` 防止在安装目录生成 Python 字节码。Windows 只装了 `python.exe` 时，可以用 `python` 替代 `py -3`。

## 原生 Windows 确定性演示

```powershell
.\scripts\run-harness-demo.ps1 -TrustBundledTests
```

脚本优先使用 PATH 上的 Python。它将两个随附的测试文件复制到新目录，确认加法测试失败，通过确定性决策修正加法，重跑加法和标签测试，并打印目标 ID 与证据数据库路径。该开关只用于已审查的本示例。它授权测试在当前 Windows 账号下运行。测试调用会导入被测源码，原生 Windows 运行时没有独立的 OS 沙箱。

```powershell
py -3 -B -m advisor_harness --db "C:\path\to\state.db" status GOAL_ID
```

如果机器的 PowerShell 策略要求签名，可以使用已签名脚本入口或手动按 WSL/Linux 示例准备工作目录。无需更改机器策略。

## WSL 或 Linux 隔离验收

在安装了 `python3`、`bubblewrap` 和 `libseccomp` 的 WSL 2 或 Linux 发行版中运行。需要内核和该环境允许 bubblewrap 使用 PID、IPC 等命名空间。优先把工作副本放在 WSL 内的 Linux 文件系统。若隔离无法启动，验收显示 BLOCKED。

```bash
run_dir=$(mktemp -d)
cp -r examples/harness/project "$run_dir/project"
python3 -B -m advisor_harness --db "$run_dir/state.db" start \
  --workspace "$run_dir/project" --policy examples/harness/policy.json \
  --provider mock --goal 'Repair calculator addition. Preserve the label and tests.'
python3 -B -m advisor_harness --db "$run_dir/state.db" status GOAL_ID
```

用于自己的代码时，先保留干净的 Git 工作副本，再以相同结构准备工作区外的 policy JSON。模型通过 policy 中的文件路径和检查别名工作，无法添加新的命令或扩大路径范围。带有命令检查的默认配置需要上述 Linux/WSL 隔离。纯文件检查可在原生 Windows 运行。

## 接入 Ollama

在运行 Harness 的同一环境启动已安装的 Ollama 服务，并确认本地已有选定模型。

```powershell
ollama list
py -3 -B -m advisor_harness --db "$env:LOCALAPPDATA\ProactiveAdvisor\state.db" start `
  --workspace "C:\path\to\project" --policy "C:\path\to\policy.json" `
  --provider "ollama:qwen3.5:9b" --goal "修复加法并保持现有标签功能"
```

默认访问当前运行环境的 IPv4 loopback 端口 11434。可添加数字端口后缀，例如 `ollama:qwen3.5:9b:11435`。WSL 下的 127.0.0.1 是否能访问 Windows 侧 Ollama 取决于 WSL 网络配置，可以在 WSL 里启动本地服务。模型需要按接口输出结构化决策。具体模型在 12 GB 显存下的速度、上下文长度和成功率须实测。

也可以用 `llama:MODEL_ALIAS:8080` 连接现有 llama.cpp 服务。Codex 是显式可选的远程决策，用 `codex:MODEL`，需要支持相应参数的本机 CLI 和有效登录。相应工作内容会作为模型输入发送，并可能消耗账户额度。参见验证报告。

## 暂停、恢复、改目标

```powershell
py -3 -B -m advisor_harness --db C:\path\state.db pause GOAL_ID
py -3 -B -m advisor_harness --db C:\path\state.db resume GOAL_ID --workspace C:\path\project --policy C:\path\policy.json
py -3 -B -m advisor_harness --db C:\path\state.db cancel GOAL_ID
py -3 -B -m advisor_harness --db C:\path\state.db revise GOAL_ID --workspace C:\path\project --policy C:\path\policy.json --goal "更新后的实际目标"
```

`start --enqueue` 保存新目标供后续执行，`resume --slice-seconds N` 以限定时段执行。可在自己的任务计划程序中对排队 ID 配置单次 `resume`，使用绝对路径、设置启动目录，并禁止新实例与现有实例并行。项目不自动创建调度任务。计算机关机且没有运行环境时，任务无法继续。原生 Windows 的已批准测试需要在恢复时重新提供 `--allow-trusted-tests`。

## 卸载

把命令指向安装目录。若在该目录存入状态库、修改安装文件或新增文件，卸载器会拒绝，保留数据。

```powershell
$Install = Join-Path $env:LOCALAPPDATA "ProactiveAdvisor\2.0"
Set-Location (Split-Path -Parent $Install)
py -3 -B (Join-Path $Install "scripts\install_harness.py") uninstall --destination $Install
```

另存的 SQLite 状态与工作副本由用户管理。原来的 Skill 卸载方式见 [安装说明](../installation.md)。
