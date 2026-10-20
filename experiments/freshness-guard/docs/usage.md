# 当前使用与安装边界

本说明日期：2026-10-20。可用性依赖账户、产品界面与实际工具；不作所有Plus账户适用的承诺。

## Skill与插件

baseline-v2.0/是历史规则快照。plugin/是当前2.0.1可分发源码，规则在plugin/skills/freshness-guard/SKILL.md。两者不应混称已在普通Chat全局启用。

仅有Skill与参考文件的插件不需要另建MCP服务器。本插件使用当前界面已有的检索能力，不提供额外搜索额度、无缓存访问或后台监控。

## 创建与使用私人插件

从仓库根目录执行：

```sh
python experiments/freshness-guard/package.py --output freshness-guard-plugin.zip
```

在实际开放Plugin Creator的账户里，让Plugin Creator用该包创建私人插件，检查服务返回的创建结果和组件诊断，再按页面提示安装。不要把普通文件附件当作安装。没有创建入口时，不保证换成ZIP就能绕过账户权限。

安装后在普通Chat的新对话输入@并选择Freshness Guard，实际提出当前事实问题。检查是否读取规则、检索并打开原文、区分时间和权限范围。私人插件创建者的链接通常不能作为所有人的公共安装地址；这里提供的是源码与重建方法。

这只能验证一次显式调用。还要另开不点名插件的任务观察自动选择，不要从一次成功推断永久全局生效。安装不会改变所有普通Chat对话的系统指令。

## 无原生安装入口的替代

将SKILL.md与references/sources.md作为项目资料/附件，并要求先读后核验。这是上下文复用，不是安装。没有代码工具时按清单人工检查，写明未执行脚本；没有检索工具时不能声称核实了当前事实。

## 官方参考

- https://learn.chatgpt.com/docs/build-skills
- https://learn.chatgpt.com/docs/skills-and-plugins
- https://learn.chatgpt.com/docs/build-plugins
- https://help.openai.com/en/articles/20001066-skills-in-chatgpt

这些链接是2026-10-20研究入口，未来政策应重新打开核查。官方支持说明不等于本账户当前可用。
