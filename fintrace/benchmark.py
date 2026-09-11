from __future__ import annotations
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from .evaluator import evaluate, VERSION
from .storage import ROOT, write_json, read_json, load_dataset


def rate(n, d):
    return {"numerator": n, "denominator": d, "rate": round(n / d, 6) if d else None}


def metrics(rows):
    wrong = [r for r in rows if r["label"]["process"] == "incorrect"]
    correct = [r for r in rows if r["label"]["process"] == "correct"]
    locatable = [r for r in wrong if r["label"]["first_error"] is not None]
    cair = [r for r in wrong if r["evaluation"]["answer_correct"] is True]
    def first(r, key):
        return (r["evaluation"].get("first_error") or {}).get(key)
    return {"count": len(rows),
            "detection": rate(sum(r["evaluation"]["process"] == "incorrect" for r in wrong), len(wrong)),
            "false_positive": rate(sum(r["evaluation"]["process"] == "incorrect" for r in correct), len(correct)),
            "localization": rate(sum(r["evaluation"]["process"] == "incorrect" and first(r, "step") == r["label"]["first_error"] for r in locatable), len(locatable)),
            "error_type": rate(sum(r['evaluation']['process'] == 'incorrect' and first(r, "type") == r["label"]["type"] for r in wrong), len(wrong)),
            "cair_recall": rate(sum(r["evaluation"]["correct_answer_invalid_process"] for r in cair), len(cair)),
            "uncertain": rate(sum(r["evaluation"]["process"] == "uncertain" for r in rows), len(rows)),
            "statuses": dict(Counter(r["evaluation"]["process"] for r in rows))}


def run_benchmark(outdir=None, split="all", mode="deterministic", resume=False):
    from .model import judge, combine, config
    if mode != "deterministic" and not config()[1]:
        raise ValueError("语义/混合对照尚不可运行：请先配置 Hy3 接口。")
    problems = {p["id"]: p for p in load_dataset()}
    samples = read_json(ROOT / "data/controlled90.json")
    if split != "all":
        samples = [s for s in samples if s["split"] == split]
    outdir = outdir or ROOT / "runs/offline"
    from pathlib import Path
    outdir = Path(outdir)
    if mode != "deterministic" and (outdir / "checkpoint.json").exists() and not resume:
        raise ValueError("该实验目录已有记录，请选择新目录或使用 --resume。")
    cfg, _ = config()
    code_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT / "fintrace").glob("*.py")))).hexdigest()
    fingerprint = hashlib.sha256(json.dumps({"samples": samples, "version": VERSION, "mode": mode,
                                 "model": cfg.get("HY3_MODEL") if mode != "deterministic" else None,
                                 "endpoint": cfg.get("HY3_BASE_URL") if mode != "deterministic" else None,
                                 "max_tokens": cfg.get("HY3_MAX_TOKENS", "8192") if mode != "deterministic" else None,
                                 "code_hash": code_hash}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    checkpoint_path = outdir / "checkpoint.json"
    checkpoint = read_json(checkpoint_path) if resume and checkpoint_path.exists() else {"fingerprint": fingerprint, "rows": {}}
    if checkpoint["fingerprint"] != fingerprint:
        raise ValueError("配置、数据或代码已变化，请使用新的输出目录，不可混合续跑。")
    rows = []
    for sample in samples:
        if sample["id"] in checkpoint["rows"]:
            row = checkpoint["rows"][sample["id"]]
            if row.get("call_status") == "complete":
                rows.append(row)
                continue
        p = problems[sample["problem_id"]]
        result = evaluate(p, sample["trace"])
        status = "complete"
        if mode != "deterministic":
            key = hashlib.sha256(sample["id"].encode()).hexdigest()[:16]
            from .model import new_run_id
            semantic = judge(p, sample["trace"], outdir / "calls" / key / new_run_id(sample["id"]))
            status = semantic["status"]
            if mode == "hybrid":
                result = combine(result, semantic)
            else:
                obj = semantic.get("output", {})
                result = {"process": obj.get("process", "uncertain"), "answer_correct": result["answer_correct"],
                          "first_error": {"step": obj.get("first_error_step"), "type": obj.get("error_type")},
                          "correct_answer_invalid_process": result["answer_correct"] is True and obj.get("process") == "incorrect",
                          "semantic": semantic, "mode": "judge"}
        row = {"id": sample["id"], "problem_id": p["id"], "split": sample["split"], "difficulty": p["difficulty"],
               "source": sample["source"], "label": sample["label"], "evaluation": result, "call_status": status}
        rows.append(row)
        checkpoint["rows"][sample["id"]] = row
        write_json(checkpoint_path, checkpoint)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "fingerprint": fingerprint, "version": VERSION,
              "mode": mode, "provenance": "controlled_synthetic_not_model_ability", "human_review": "pending",
              "overall": metrics(rows), "by_split": {s: metrics([r for r in rows if r["split"] == s]) for s in ("dev", "test")},
              "by_difficulty": {b: metrics([r for r in rows if r["difficulty"] == b]) for b in ("easy", "medium", "hard")},
              "by_error": {k: metrics([r for r in rows if r["label"]["type"] == k]) for k in sorted({r["label"]["type"] for r in rows if r["label"]["type"]})},
              "call_statuses": dict(Counter(r["call_status"] for r in rows)),
              "pending": ["人工证据/语义标签复核", "真实 Hy3 解答实验"] + (["Hy3 语义与混合对照"] if mode == "deterministic" else [])}
    write_json(outdir / "results.json", rows)
    write_json(outdir / "summary.json", report)
    with (outdir / "results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "split", "difficulty", "source", "gold_process", "pred_process", "gold_first", "pred_first", "answer_correct", "call_status"])
        for r in rows:
            w.writerow([r["id"], r["split"], r["difficulty"], r["source"], r["label"]["process"], r["evaluation"]["process"],
                        r["label"]["first_error"], (r["evaluation"]["first_error"] or {}).get("step"), r["evaluation"]["answer_correct"], r["call_status"]])
    lines = ["# FinTrace 受控样本评估报告", "", "按原始构造标签评估相同样本，记录每项指标的分子与分母。", "",
             f"评估器：{VERSION}；模式：{mode}；样本：{len(rows)}", "", "|指标|开发集|评测集|", "|---|---|---|"]
    for key, title in [("detection", "错误检出率"), ("false_positive", "正确过程误报率"), ("localization", "首错定位准确率"),
                       ("error_type", "错误类型准确率"), ("cair_recall", "答案对过程错识别率"), ("uncertain", "无法确定比例")]:
        vals = []
        for s in ("dev", "test"):
            x = report["by_split"][s][key]
            vals.append(f"{x['numerator']}/{x['denominator']}" + (f"（{x['rate']:.1%}）" if x["rate"] is not None else "（不适用）"))
        lines.append(f"|{title}|{'|'.join(vals)}|")
    lines += ["", "公式变更而局部算术及说明一致的样本可能返回无法确定；公式与明确说明矛盾时可直接定位。",
              "定位和检出分母包含未检出及无法判断的错误样本。标签来源为受控构造。",
              "本结果用于规则回归检查。说明一致性检查的独立贡献和消融结果见 runs/experiments/batch-v2/REPORT.md。"]
    (outdir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
