# 参与贡献

欢迎提交可复现的问题、文档修正和部署改进。先查阅[文档目录](docs/README.md)和现有 Issues；较大的行为调整可以先说明使用场景，再提交 PR。

## 本地开发

需要 Python 3.10+、Bash、ShellCheck，以及支持 `config --format json` 的 Docker Compose v2。Python 不需要第三方依赖；Compose 测试不连接 daemon。Ubuntu 部署步骤仍以 Ubuntu 26.04 为目标。

```bash
make check
```

`make check` 检查文档本地链接、锚点和 Bash 示例语法、Shell 脚本并运行现有测试。只运行测试用 `make test`，检查文档用 `make docs`。缺少 Docker CLI 时 unittest 会跳过 Compose 测试；提交前安装 Compose 并确保该测试实际通过，CI 会先检查 Compose 可用性。

测试使用临时目录、模拟命令和虚构摘要。不要在本地运行 init-state、preflight、audit 或 backup，也不要用生产 `/data` 验证改动。真实服务器验收与本地测试分别记录。

## 修改位置

部署参数改 `.env.example` 和[字段说明](docs/reference.md)；行为改 Compose、脚本或 `traefik/templates/`。不编辑生成配置，不提交有效 `.env`、secrets、ACME 文件、Token、对象数据或备份。

新 provider 应包含凭据准备文档、生成器行为、预检查和三种模式之外的新合并测试。安全默认值变化需要说明访问影响和回退方法；保留不挂载 Docker socket、后端端口绑定本机、非 root 身份和独立网络的边界。

步骤统一维护在任务文档。移动文件时更新导航与相对链接，保留命令的执行位置、权限和失败处理。`scripts/` 和 Compose 路径是对外部署接口，修改时说明如何同步安装文件；不要仅为了目录整齐移动这些文件。

## 提交 PR

说明触发条件、修改后的行为、验证结果和未验证项。文档改动检查命令、版本、链接和代码围栏；运行行为改动添加能验证风险的测试。按[上线验收](docs/validation.md)记录必要的实际服务检查，不将模拟测试写成生产验收。

涉及模板行为的变化记入 [CHANGELOG](CHANGELOG.md) 的 Unreleased；上游软件升级仍核对发布说明、摘要和兼容性。贡献内容按本仓库 [Apache-2.0](LICENSE) 许可证提供。

发现凭据泄露或可利用问题时按[安全说明](SECURITY.md)报告，不在公开 Issue 粘贴秘密。
