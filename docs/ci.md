# CI 配置草案（尚未启用）

本次本地十五项工具测试通过，但 GitHub OAuth 凭据缺少 `workflow` scope，平台拒绝新增 `.github/workflows/checks.yml`。因此当前仓库没有启用这份 Actions 工作流，没有远程 CI 通过结果。

具有相应权限的维护者可以在 GitHub 网页创建 `.github/workflows/checks.yml`，或在自己的 CLI 会话补充 workflow 授权后提交下列配置。请按账号界面完成授权，不分享验证码或 token。该工作流只检查项目工具，不调用模型、不证明 Skill 行为收益。

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

English: this workflow is a reviewed draft, not an enabled CI check. Publishing it was rejected because the current OAuth credential lacks the `workflow` scope. An appropriately authorized maintainer can create the file shown above in the GitHub UI or submit it after granting that scope. No model calls are included.
