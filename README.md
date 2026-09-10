# FinTrace · 财务推理过程评估与错误定位

基于 Hy3 和 FinQA 的财务推理评估工作台。将财报中的原始证据、结构化计算步骤与评估结论连接起来，分别检查**答案是否正确、过程是否成立、错误最先出现在哪里**。

个人项目，面向腾讯犀牛鸟开源实战任务「可验证场景：过程评估与错误定位」。

[演示视频](demo/fintrace-demo.mp4) · [项目说明](docs/SUBMISSION.md) · [实验报告](runs/experiments/batch-v1/REPORT.md) · [方法与指标](docs/METHOD.md)

[![FinTrace 工作台预览](demo/poster.png)](demo/fintrace-demo.mp4)

## 项目特点

- **答案与过程独立判定**：识别最终答案正确、中间推导有误的案例。
- **证据追踪**：点击计算步骤，定位财报表格、文字与取数位置。
- **首错定位与错误传播**：区分本步独立错误和继承上游错误的步骤。
- **三种评估方式**：确定性规则、Hy3 语义评审、规则与语义结合的混合评估。
- **可交互工作台**：案例切换、JSON 编辑重评、批量对照、案例复核与结果导出。
- **可复现实验**：固定数据版本，保存逐题结果、评价口径与运行配置。

例如，将 `8 + 14` 写成 `23`，却在最终答案中填写正确的 `22`。FinTrace 会分别给出“答案正确”和“过程错误”，并将计算错误定位到第一步。

## 快速开始

环境要求：Python 3.11 或以上。核心程序与网页仅使用标准库和原生 HTML / CSS / JavaScript。

```sh
git clone https://github.com/yangkevinykw/hy3-fintrace.git
cd hy3-fintrace
python -X utf8 scripts/serve_batch_workbench.py
```

启动后，在浏览器访问：[http://127.0.0.1:8765/](http://127.0.0.1:8765/)

Windows 用户也可以双击仓库根目录中的 `启动工作台.cmd`。

仓库自带题集、受控案例和真实解答记录，可直接查看演示、重评案例和浏览实验结果。新增 Hy3 解答时，按下文配置接口。

## 工作台功能

| 页面 | 功能 |
| --- | --- |
| 推理工作台 | 查看原始证据、计算轨迹、首错位置和判定依据；编辑解答后重新评估 |
| 批量评测 | 比较三种评估方式，查看分组指标、参考争议和保存的 Hy3 解答 |
| 案例复核 | 在初次提交前隐藏评估结论，记录判断、首错位置和依据 |

## 实验结果

数据来自固定版本的 FinQA：选取 30 道题，按参考计算步数分为三个难度层级，每层 10 题；按财报隔离为 10 道开发题和 20 道评测题。每题构造一个参考过程和两个错误过程，共 90 个受控样本。

| 验证内容 | 结果 |
| --- | --- |
| 项目测试 | 36 项通过 |
| 官方执行器交叉核验 | 30 / 30 一致 |
| Hy3 真实解答与语义评审 | 30 / 30 成功 |
| 真实答案与原始 FinQA 程序符合 | 20 / 30 |
| 规则组错误检出 | 45 / 60 |
| 混合组错误检出 | 57 / 60 |
| 规则组、混合组对参考过程的误报 | 均为 0 / 30 |

受控实验按原始构造标签统计，失败与弃权保留在分母中；它衡量评估器对这组样本的表现。真实解答另以原始 FinQA 程序结果为参照。逐题依据、参考争议、调用记录和敏感性分析见[完整实验报告](runs/experiments/batch-v1/REPORT.md)。

## 评估流程

```text
财报表格 / 报告文字 + 问题
              ↓
结构化解答：证据、公式、步骤、答案
              ↓
确定性规则核验 + Hy3 语义评审
              ↓
混合评估 → 首错定位 → 错误传播
              ↓
工作台展示 / 批量报告 / 结果导出
```

规则组核验证据数值、步骤依赖、局部运算、答案衔接与符号等价性。Hy3 评审补充公式和财务含义的判断。混合组保留已确认的规则错误，同时记录语义评审及分歧。证据不足时返回“无法确定”。

## 配置 Hy3

复制 `.env.example` 为 `.env`，填写服务商提供的接口配置：

```dotenv
HY3_API_KEY=你的密钥
HY3_BASE_URL=服务商提供的基础地址
HY3_MODEL=可用的模型名称
HY3_TIMEOUT=180
HY3_MAX_TOKENS=8192
```

接口使用 HTTPS 基础地址下的 `/chat/completions` 协议。密钥仅从本地环境变量或 `.env` 读取；`.env` 已加入 Git 忽略规则。

```sh
# 检查配置，不显示密钥
python -m fintrace status

# 生成一份解答及语义评审
python -m fintrace live --limit 1 --judge --out runs/live/example
```

## 测试与复现

```sh
# 运行项目测试
python -X utf8 -m unittest discover -s tests -v

# 重算 90 个受控样本
python -X utf8 -m fintrace benchmark

# 单独评估测试划分
python -X utf8 -m fintrace benchmark --split test --out runs/test

# 交叉核验官方计算结果
python -X utf8 scripts/verify_official.py
```

在线实验与批次运行方法见[实验协议](docs/BATCH_PROTOCOL.md)。上游 FinQA 版本固定为 `0f16e2867befa6840783e58be38c9efb9229d742`，来源、文件哈希和筛选统计见[数据清单](data/manifest.json)。

## 项目结构

```text
fintrace/          数据转换、计算执行器、评估器、Hy3 接口与网页
data/              固定题集、受控过程、来源与许可
tests/             算术、协议、评估指标和本地接口测试
scripts/           数据准备、批量实验、交叉核验与演示制作
runs/offline/      离线评估报告与逐题结果
runs/experiments/  批量实验汇总与真实解答
demo/              演示视频、字幕和操作说明
docs/              项目说明、方法、实验协议和验证记录
```

## 文档

| 文档 | 内容 |
| --- | --- |
| [项目说明](docs/SUBMISSION.md) | 项目目标、主要功能、演示入口 |
| [方法与指标](docs/METHOD.md) | 证据映射、计算核验、首错定义与指标分母 |
| [实验报告](runs/experiments/batch-v1/REPORT.md) | 三组对照、逐题争议与运行记录 |
| [验证记录](docs/VALIDATION.md) | 测试、交叉核验与浏览器检查 |
| [功能清单](docs/IMPLEMENTATION_STATUS.md) | 数据、评估、接口与工作台能力 |
| [演示说明](docs/DEMO.md) | 视频入口与操作顺序 |

## 许可

项目代码采用 [MIT License](LICENSE)。FinQA 数据与上游代码保留其[原始许可](data/source/FinQA-LICENSE.txt)和出处。
