# 结构化解答格式

最小示例（证据 ID 必须来自实际题目的 evidence 字段）：

```json
{
  "steps": [
    {
      "id": "s1",
      "op": "subtract",
      "args": [
        {"kind": "evidence", "ref": "t:1:1:0", "value": "120"},
        {"kind": "evidence", "ref": "t:1:2:0", "value": "100"}
      ],
      "result": "20",
      "explanation": "计算两个年份的收入差。"
    },
    {
      "id": "s2",
      "op": "divide",
      "args": [
        {"kind": "step", "ref": "s1"},
        {"kind": "evidence", "ref": "t:1:2:0", "value": "100"}
      ],
      "result": "0.2",
      "explanation": "以基期收入为分母计算增长率。"
    }
  ],
  "final": {"value": "0.2", "unit": "ratio"}
}
```

- 步骤必须按 s1/s2/... 连续编号，最多 24 步；每步两个操作数。
- op 支持 add/subtract/multiply/divide。
- args.kind=evidence 时，ref 指向证据，value 是证据的归一化数值。
- args.kind=step 时，ref 指向前序步骤；它的声称结果作为本步输入。
- args.kind=constant 时，value 是数学常量；不得把题中财务数字伪装为常量。
- result 是数值字符串，必须与最后的 final.value 保持同一数值尺度；避免中途截断或过度舍入。
- final.unit 支持 number/ratio/percent。percent 时 value=20 代表 20%，不要再写 %；ratio 时 value=0.2。
- 从比例 0.2 转为百分数 20 必须增加显式乘以 100 的步骤。评估时将候选和标准答案按各自单位统一到比例尺度。
- 不支持的指令或不明确的单位应保留失败/无法确定，不猜测模型意图。

运行本地解答文件：

    python -m fintrace evaluate --problem 实际题目ID --trace trace.json --out result.json

输出包含 process、answer_correct、first_error、localization、reference_equivalent、findings 和逐步结果。每条 finding 带类型、步骤、判定依据；后续受影响步骤使用 affected_by。
