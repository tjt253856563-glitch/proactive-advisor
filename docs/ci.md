# CI 检查范围

工作流文件：[.github/workflows/checks.yml](../.github/workflows/checks.yml)。推送与 Pull Request 触发 Windows/Linux 和 Python 3.10/3.12 的四组检查，运行项目工具测试及 Python 编译检查。

每次运行是否通过，以 [GitHub Actions](https://github.com/tjt253856563-glitch/proactive-advisor/actions/workflows/checks.yml) 中对应提交的实际记录为准。配置存在不能代替运行成功。

测试验证安装/卸载保护、配对夹具、日志与差异记录、故障/超时分类及评分证据要求，使用本地模拟适配器，不调用在线模型、不消耗模型额度。**CI 通过不证明 Skill 行为收益**，也不验证所有客户端的发现机制、自动触发或外部用户体验。

初次提交曾因 OAuth 凭据缺少 workflow scope 被拒绝。维护者补充授权后才提交活动工作流，旧限制说明保留在项目历史中。配置如下：

```yaml
name: Project checks
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  infrastructure:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ['3.10', '3.12']
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m unittest discover -s tests -v
      - run: python -m compileall -q scripts evals skills/proactive-advisor
```

English: the workflow runs infrastructure tests and Python compilation on Windows/Linux with Python 3.10/3.12. Tests use local fake adapters and make no model calls. Passing CI is not evidence of a behavioral improvement, automatic skill invocation or external adoption. Consult the Actions run for the exact commit. The initial permission issue was resolved by the maintainer granting the workflow scope.
