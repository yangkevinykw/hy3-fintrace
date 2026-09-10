# 数据来源与复现

原始数据：FinQA（EMNLP 2021），https://github.com/czyssrs/FinQA 。

- 固定提交：`0f16e2867befa6840783e58be38c9efb9229d742`。
- 上游许可：MIT，完整文本保存在 `source/FinQA-LICENSE.txt`。
- `source/finqa30_raw.json` 保存入选题目的必要原始字段，没有将 78MB 的全量下载缓存提交到项目。
- `finqa30.json` 是位置化证据与标准程序转换结果。
- `controlled90.json` 包含 trace、单独的构造标签和修改前后记录。
- `manifest.json` 保存来源 URL/哈希、筛选规则、排除统计、划分和待人工复核状态。

复现：先运行 `python scripts/download_finqa.py`，再运行 `python -m fintrace build-data`。已有子集可以完全离线运行，不必重新下载全量数据。

筛选偏向四则运算、证据容易自动对齐的题目，因此不能外推为整个 FinQA 的无偏代表。难度仅按参考计算步数划分；不是对模型真实难度的证明。来自同一报告的题目不会跨开发/评测组，但同一公司的不同报告仍可能出现在两组，不能声称公司级隔离。

引用：Chen et al. (2021), FinQA: A Dataset of Numerical Reasoning over Financial Data, EMNLP 2021.
