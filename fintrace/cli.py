from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .storage import ROOT, read_json, write_json, load_dataset


def main():
    parser = argparse.ArgumentParser(description="FinTrace 财务推理过程评估")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="查看本地接口配置状态，不显示密钥")
    commands.add_parser("build-data", help="从已下载的固定版本 FinQA 重建题集")
    bench = commands.add_parser("benchmark", help="受控样本验证；与真实模型实验分开")
    bench.add_argument("--split", choices=["all", "dev", "test"], default="all")
    bench.add_argument("--mode", choices=["deterministic", "judge", "hybrid"], default="deterministic")
    bench.add_argument("--out", type=Path, default=ROOT / "runs/offline")
    bench.add_argument("--resume", action="store_true")
    evaluate = commands.add_parser("evaluate", help="评估本地结构化解答 JSON")
    evaluate.add_argument("--problem", required=True)
    evaluate.add_argument("--trace", required=True, type=Path)
    evaluate.add_argument("--out", type=Path, required=True)
    live = commands.add_parser("live", help="真实 Hy3 解答实验；不会使用模拟输出")
    live.add_argument("--split", choices=["all", "dev", "test"], default="dev")
    live.add_argument("--limit", type=int, default=1)
    live.add_argument("--judge", action="store_true")
    live.add_argument("--out", type=Path, default=ROOT / "runs/live/experiment")
    live.add_argument("--resume", action="store_true")
    serve = commands.add_parser("serve", help="启动本地浏览器工作台")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "status":
            from .model import public_config
            result = public_config()
        elif args.command == "build-data":
            from .dataset import build
            build()
            return
        elif args.command == "benchmark":
            from .benchmark import run_benchmark
            result = run_benchmark(args.out, args.split, args.mode, args.resume)
        elif args.command == "evaluate":
            from .evaluator import evaluate
            p = next((p for p in load_dataset() if p["id"] == args.problem), None)
            if p is None:
                raise ValueError("未知题目编号")
            result = evaluate(p, read_json(args.trace))
            write_json(args.out, result)
        elif args.command == "live":
            result = run_live(args)
        else:
            from .server import serve
            serve(args.port)
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"FinTrace: {exc}\n")


def run_live(args):
    from .model import config, solve, judge, combine, SOLVER_PROMPT, JUDGE_PROMPT
    from .evaluator import evaluate
    if not config()[1]:
        raise ValueError("尚未配置 Hy3；请在 .env 填写接口、模型和密钥后再运行。")
    problems = [p for p in load_dataset() if args.split == "all" or p["split"] == args.split]
    if args.limit <= 0:
        raise ValueError("limit 必须大于零")
    problems = problems[:args.limit]
    cfg, _ = config()
    code_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT / "fintrace").glob("*.py")))).hexdigest()
    fingerprint = hashlib.sha256(json.dumps({"problems": problems, "solver": SOLVER_PROMPT, "judge": JUDGE_PROMPT if args.judge else None,
                                 "model": cfg["HY3_MODEL"], "endpoint": cfg["HY3_BASE_URL"], "max_tokens": cfg.get("HY3_MAX_TOKENS", "8192"), "code_hash": code_hash}, sort_keys=True).encode()).hexdigest()
    manifest_path = args.out / "manifest.json"
    if manifest_path.exists():
        if not args.resume:
            raise ValueError("输出目录已有实验；请指定新目录或 --resume。")
        if read_json(manifest_path)["fingerprint"] != fingerprint:
            raise ValueError("实验配置不一致，请使用新的输出目录。")
    write_json(manifest_path, {"fingerprint": fingerprint, "provenance": "hy3_live", "count": len(problems)})
    results = []
    for p in problems:
        key = hashlib.sha256(p["id"].encode()).hexdigest()[:16]
        folder = args.out / key
        saved = folder / "result.json"
        if args.resume and saved.exists() and read_json(saved)["status"] == "complete":
            results.append(read_json(saved))
            continue
        from .model import new_run_id
        attempt_folder = folder / new_run_id(p["id"])
        response = solve(p, attempt_folder)
        row = {"problem_id": p["id"], "source": "hy3_live", "split": p["split"], "difficulty": p["difficulty"], **response}
        if response["status"] == "complete":
            row["evaluation"] = evaluate(p, response["output"])
            if args.judge:
                semantic = judge(p, response["output"], attempt_folder)
                row["evaluation"] = combine(row["evaluation"], semantic)
                if semantic["status"] != "complete":
                    row["status"] = "judge_failed"
        write_json(attempt_folder / "result.json", row)
        write_json(saved, row)
        results.append(row)
        write_json(args.out / "results.json", results)
        print(f"{len(results)}/{len(problems)} {p['id']}: {row['status']}", flush=True)
    from .benchmark import rate
    successful = [r for r in results if r.get("evaluation")]
    summary = {"provenance": "hy3_live", "total": len(results),
               "generation_success": rate(len(successful), len(results)),
               "answer_accuracy_all_attempts": rate(sum(r["evaluation"]["answer_correct"] is True for r in successful), len(results)),
               "process_pass_all_attempts": rate(sum(r["evaluation"]["process"] == "correct" for r in successful), len(results)),
               "note": "过程结果为评估器判定，未经过人工确认；失败调用计入总分母。"}
    write_json(args.out / "summary.json", summary)
    return summary


if __name__ == "__main__":
    main()
