# Proactive Advisor 2.0 验证记录

- [现有项目与测试基线](baseline.md)
- [首轮真实模型结果，包括全部失败](evidence/real-model-pilot.json)
- [确定性基础设施对照](evidence/mock-control.json)

首轮模型试验使用本次任务的临时 Linux CPU 环境。模型为公开 Qwen2.5-Coder-1.5B-Instruct Q4_K_M，服务为 llama.cpp。该结果不代表用户的 Windows、RTX GPU 或 Ollama 实跑。首轮 A 和 B 均未有样本通过，发生了重复读取、结构化输出错误、遗漏验收检查以及未精确匹配编辑片段。后续修复针对这些具体问题并重跑配对。
