"""Compare FinTrace arithmetic against the pinned official FinQA evaluator.

Only four audited function definitions and all_ops are loaded. The upstream CLI,
imports and file-handling entrypoint are not executed. Candidate code is never run.
"""
import ast
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fintrace.storage import ROOT, read_json, write_json
from fintrace.core import execute_program, close, number

EXPECTED = "845cd131cab843eceff256cf6d392978cc470a7da4a80107beb56027fdca5c13"


def main():
    payload = (ROOT / "data/cache/code_evaluate_evaluate.py").read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED:
        raise ValueError("Official source hash mismatch")
    tree = ast.parse(payload.decode())
    names = {"str_to_num", "process_row", "eval_program", "program_tokenization"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names or
             isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "all_ops" for t in n.targets)]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pinned_finqa_evaluator", "exec"), namespace)
    rows = []
    for p in read_json(ROOT / "data/finqa30.json"):
        source = p["source"]["program"]
        flag, official = namespace["eval_program"](namespace["program_tokenization"](source), p["table"])
        ours = execute_program(source)[-1]
        passed = flag == 0 and close(ours, number(official)) and close(ours, number(p["answer"]["value"]))
        rows.append({"id": p["id"], "official": official, "fintrace": str(float(ours)), "passed": passed})
    report = {"source_sha256": EXPECTED, "passed": sum(r["passed"] for r in rows), "total": len(rows), "rows": rows}
    write_json(ROOT / "runs/offline/official_crosscheck.json", report)
    print(json.dumps({"passed": report["passed"], "total": report["total"]}))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
