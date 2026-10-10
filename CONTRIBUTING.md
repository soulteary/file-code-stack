# 参与贡献

欢迎提交可复现的问题、文档修正和部署改进。先查阅[文档目录](docs/README.md)和现有 Issues；较大的行为调整可以先说明使用场景，再提交 PR。

## 本地开发

需要 Python 3.10+、Bash、ShellCheck，以及支持 `config --format json` 的 Docker Compose v2。Python 不需要第三方依赖；Compose 测试不连接 daemon。Ubuntu 部署步骤仍以 Ubuntu 26.04 为目标。

```bash
make check
```

`make check` 检查文档本地链接、锚点和 Bash 示例语法、Shell 脚本并运行现有测试。只运行测试用 `make test`，检查文档用 `make docs`。缺少 Docker CLI 时 unittest 会跳过 Compose 测试；提交前安装 Compose 并确保该测试实际通过，CI 会先检查 Compose 可用性。

测试使用临时目录、模拟命令和虚构摘要。不要在本地运行 init-state、preflight、audit 或 backup，也不要用生产 `/data` 验证改动。真实服务器验收与本地测试分别记录。

## 单独验证配置生成器

```bash
make test-render
# 或直接运行：
python3 tests/test_render_cli.py
```

这个测试程序在临时目录复制生成脚本和模板，从其他工作目录实际执行 CLI，读取生成的三个文件。它不导入生成器，也不使用生成器计算预期结果。`tests/fixtures/render/` 保存独立预期配置，比较完整解析内容，同时检查文件权限、占位符和 `--check` 不改写文件的行为。

证书与 Git 初始化开关组成 24 个有效组合，覆盖 HTTP-01、两种 DNS-01、旧泛域名模式、多个普通域名、多个泛域名、混合域名和被覆盖域名的省略。错误参数、缺失或被修改的输出、模板占位符和模式切换同样检查，失败时三个现有文件的内容、权限与修改时间应保持原样。

CI 额外运行 `render-configurations` 矩阵：12 个独立任务，每个检查 Git 初始化开关的 true/false，共 24 个有效配置。PR 和 main 的 push 都会触发，某个组合失败不会取消其他组合。原来的 `make check` 继续检查完整测试集和错误输入。

本地可以复现某一个 CI 任务：

```bash
python3 tests/test_render_cli.py --provider cloudflare --certificate-case mixed-covered
```

`--provider` 可选 `http`、`alidns`、`cloudflare`；`--certificate-case` 可选 `hosts`、`legacy`、`explicit-hosts`、`multiple-wildcards`、`mixed-covered`。包含泛域名的任务仅使用 DNS-01。没有匹配组合时测试失败，不会空跑后报告成功。

该程序只需要 Python 3.10+，不用 Docker 或网络，不读取真实 `.env`，不启动服务或申请证书。`make test` 和 CI 的 `make check` 也会自动运行它。变更输出合同时人工审阅并更新预期配置，不直接用生成器输出覆盖这些基准，否则可能把错误一起保存为预期结果。

## 修改位置

部署参数改 `.env.example` 和[字段说明](docs/reference.md)；行为改 Compose、脚本或 `traefik/templates/`。不编辑生成配置，不提交有效 `.env`、secrets、ACME 文件、Token、对象数据或备份。

新 provider 应包含凭据准备文档、生成器行为、预检查和三种模式之外的新合并测试。安全默认值变化需要说明访问影响和回退方法；保留不挂载 Docker socket、后端端口绑定本机、非 root 身份和独立网络的边界。

步骤统一维护在任务文档。移动文件时更新导航与相对链接，保留命令的执行位置、权限和失败处理。`scripts/` 和 Compose 路径是对外部署接口，修改时说明如何同步安装文件；不要仅为了目录整齐移动这些文件。

## 提交 PR

说明触发条件、修改后的行为、验证结果和未验证项。文档改动检查命令、版本、链接和代码围栏；运行行为改动添加能验证风险的测试。按[上线验收](docs/validation.md)记录必要的实际服务检查，不将模拟测试写成生产验收。

涉及模板行为的变化记入 [CHANGELOG](CHANGELOG.md) 的 Unreleased；上游软件升级仍核对发布说明、摘要和兼容性。贡献内容按本仓库 [Apache-2.0](LICENSE) 许可证提供。

发现凭据泄露或可利用问题时按[安全说明](SECURITY.md)报告，不在公开 Issue 粘贴秘密。
