"""Deterministic evaluator. Mutation labels and expected verdicts are never read."""
from __future__ import annotations
from .core import (OPS, number, calculate, render, close, calculation_close, symbol, constant,
                   expression, equivalent)

VERSION = "fintrace-rules-0.3"
CONSTANTS = {"-1", "0", "1", "2", "3", "4", "12", "100", "1000", "1000000"}


def evaluate(problem, trace):
    findings, rows = [], []
    values, exprs, dependencies = {}, {}, {}
    unknown = False

    def finding(step, kind, message, evidence=None, status="incorrect"):
        findings.append({"step": step, "type": kind, "status": status,
                         "message": message, "evidence": evidence or {}})

    if not isinstance(trace, dict):
        trace = {}
    steps = trace.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 24:
        steps = []
        finding(None, "format", "需要 1–24 个结构化步骤")
    seen = set()
    for pos, step in enumerate(steps, 1):
        sid = f"s{pos}"
        start = len(findings)
        row = {"id": sid, "position": pos, "status": "correct", "computed": None,
               "claimed": None, "evidence_refs": [], "affected_by": []}
        dependencies[sid] = []
        if not isinstance(step, dict):
            finding(sid, "format", "步骤必须是对象")
            row["status"] = "incorrect"
            rows.append(row)
            continue
        if step.get("id") != sid or sid in seen:
            finding(sid, "format", f"步骤编号必须连续，当前应为 {sid}")
        seen.add(sid)
        op, args = step.get("op"), step.get("args")
        row.update({"op": op, "explanation": str(step.get("explanation", ""))[:4000], "claimed": step.get("result")})
        if not isinstance(op, str) or op not in OPS or not isinstance(args, list) or len(args) != 2:
            finding(sid, "format", "每一步需包含支持的运算符及两个操作数")
        else:
            nums, syms = [], []
            for arg in args:
                try:
                    if not isinstance(arg, dict):
                        raise ValueError("操作数必须是对象")
                    kind = arg.get("kind")
                    if kind == "step":
                        ref = arg.get("ref")
                        if not isinstance(ref, str) or ref not in dependencies or ref == sid:
                            finding(sid, "dependency", "步骤引用不存在或不是前序步骤", {"ref": ref})
                            raise ValueError("无法读取引用步骤")
                        dependencies[sid].append(ref)
                        if ref not in values:
                            finding(sid, "upstream_unavailable", "上游步骤没有可用结果", {"ref": ref}, "uncertain")
                            raise ValueError("上游无法执行")
                        nums.append(values[ref])
                        syms.append(exprs.get(ref))
                    elif kind == "evidence":
                        ref = arg.get("ref")
                        source = problem["evidence"].get(ref) if isinstance(ref, str) else None
                        row["evidence_refs"].append(ref)
                        if source is None:
                            finding(sid, "evidence_missing", "引用的原始证据位置不存在", {"ref": ref})
                            raise ValueError("证据不存在")
                        n = number(arg.get("value"))
                        if n != number(source["value"]):
                            finding(sid, "evidence_value", "取数与引用证据中的数值不一致", {"ref": ref, "expected": source["value"], "actual": arg.get("value"), "text": source["text"]})
                        nums.append(n)
                        syms.append(symbol(ref))
                    elif kind == "constant":
                        n = number(arg.get("value"))
                        if render(n) not in CONSTANTS:
                            finding(sid, "unproven_constant", "该常量需要解释其来源，不能代替财务证据", status="uncertain")
                        nums.append(n)
                        syms.append(constant(render(n)))
                    else:
                        raise ValueError("未知操作数类型")
                except (ValueError, TypeError, KeyError):
                    if len(findings) == start:
                        finding(sid, "format", "操作数格式或数值无效")
            if len(nums) == 2:
                try:
                    computed = calculate(op, *nums)
                    row["computed"] = render(computed)
                    claimed = number(step.get("result"))
                    values[sid] = claimed  # Verify downstream locally against stated inputs.
                    if not calculation_close(computed, claimed):
                        finding(sid, "arithmetic", "本步计算结果与所列操作数不一致", {"expected": render(computed), "actual": step.get("result")})
                    if all(x is not None for x in syms):
                        exprs[sid] = expression(op, *syms)
                except (ValueError, TypeError, OverflowError):
                    finding(sid, "execution", "除零、无效结果或计算预算超限")
        current = findings[start:]
        row["status"] = "incorrect" if any(x["status"] == "incorrect" for x in current) else ("uncertain" if current else "correct")
        rows.append(row)

    expected = number(problem["answer"]["value"])
    final_correct, final_value = None, None
    final = trace.get("final")
    try:
        if not isinstance(final, dict) or final.get("unit") not in ("number", "ratio", "percent"):
            raise ValueError("答案缺少单位")
        final_raw = number(final["value"])
        final_value = final_raw
        if final["unit"] == "percent":
            # A percent final value is a plain number, e.g. 20 represents 20%.
            if "%" in str(final["value"]):
                raise ValueError("percent 单位的 value 不应重复包含 %")
            final_value /= 100
        answer_in_source_scale = final_value * (100 if problem["answer"]["unit"] == "percent" else 1)
        final_correct = close(answer_in_source_scale, expected)
        if steps and f"s{len(steps)}" in values:
            if not calculation_close(values[f"s{len(steps)}"], final_raw):
                finding("final", "answer_consistency", "最终答案数值与最后一步不一致；单位换算须显式列为步骤", {"last_result": render(values[f"s{len(steps)}"]), "final": render(final_raw)})
        else:
            finding("final", "upstream_unavailable", "最后一步缺少有效结果", status="uncertain")
    except (ValueError, KeyError, TypeError):
        finding("final", "format", "最终答案格式无效；需填写 value 和 number/ratio/percent 单位")

    # Build exact expressions from the gold structured reference (no sample labels).
    reference_exprs = {}
    try:
        for s in problem["reference"]["steps"]:
            parts = []
            for a in s["args"]:
                parts.append(reference_exprs[a["ref"]] if a["kind"] == "step" else symbol(a["ref"]) if a["kind"] == "evidence" else constant(a["value"]))
            reference_exprs[s["id"]] = expression(s["op"], *parts)
        last = exprs.get(f"s{len(steps)}")
        reference = reference_exprs[problem["reference"]["steps"][-1]["id"]]
        if last is not None and isinstance(final, dict) and final.get("unit") == "percent":
            last = expression("divide", last, constant("100"))
        if problem["reference"]["final"]["unit"] == "percent":
            reference = expression("divide", reference, constant("100"))
        formula_equivalent = last is not None and equivalent(last, reference)
    except (ValueError, KeyError, TypeError):
        formula_equivalent = None
    if not formula_equivalent:
        unknown = True
        finding(None, "semantic_unverified", "尚未证明候选公式与标准证据计算等价；差异本身不作为错误结论", status="uncertain")

    hard = [f for f in findings if f["status"] == "incorrect"]
    order = {f"s{i}": i for i in range(1, len(steps) + 1)} | {None: 0, "final": len(steps) + 1}
    hard.sort(key=lambda f: order.get(f["step"], 0))
    first = hard[0] if hard else None
    hard_steps = {f["step"] for f in hard}
    for row in rows:
        refs = dependencies[row["id"]]
        affected = set()
        for ref in refs:
            if ref in hard_steps:
                affected.add(ref)
            for prior in rows:
                if prior["id"] == ref:
                    affected.update(prior["affected_by"])
        row["affected_by"] = sorted(affected)
        if affected and row["status"] == "correct":
            row["status"] = "affected"
    earlier_uncertain = first and any(f["status"] == "uncertain" and order.get(f["step"], 0) < order[first["step"]] for f in findings)
    process = "incorrect" if hard else ("uncertain" if unknown or any(f["status"] == "uncertain" for f in findings) else "correct")
    return {"version": VERSION, "mode": "deterministic", "problem_id": problem["id"],
            "scope": "结构化证据与计算；自然语言解释未由规则证明", "process": process,
            "answer_correct": final_correct, "normalized_answer": render(final_value) if final_value is not None else None,
            "reference_equivalent": formula_equivalent, "first_error": first,
            "localization": "earliest_confirmed" if earlier_uncertain else "exact_in_supported_checks" if first else "none",
            "correct_answer_invalid_process": final_correct is True and process == "incorrect",
            "steps": rows, "findings": findings}
