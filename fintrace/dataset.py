"""Import pinned FinQA data and construct labeled, explicitly synthetic traces."""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import hashlib
import json
from .core import NUMBER, number, parse_program, execute_program, render, close, calculate
from .storage import ROOT, read_json, write_json


def collect_evidence(raw):
    evidence = {}
    def extract(prefix, text, group, location):
        seen = set()
        for match in NUMBER.finditer(text):
            try:
                n = number(match.group().strip())
            except ValueError:
                continue
            if n in seen:
                continue
            seen.add(n)
            key = f"{prefix}:{len(seen)-1}"
            evidence[key] = {"value": render(n), "token": match.group().strip(), "text": text,
                             "group": group, "location": location, "span": [match.start(), match.end()]}
    for r, row in enumerate(raw["table"]):
        for c, cell in enumerate(row):
            extract(f"t:{r}:{c}", str(cell), f"table_{r}", {"kind": "table", "row": r, "col": c})
    for i, text in enumerate(raw.get("pre_text", []) + raw.get("post_text", [])):
        extract(f"x:{i}", text, f"text_{i}", {"kind": "text", "index": i})
    return evidence


def normalize(raw):
    qa = raw["qa"]
    program = parse_program(qa["program"])
    outputs = execute_program(qa["program"])
    expected = number(qa["exe_ans"])
    if not close(outputs[-1], expected) or abs(expected) > 10**9:
        raise ValueError("standard_execution_mismatch")
    answer_unit = "number"
    answer_text = str(qa.get("answer", "")).strip()
    if answer_text.endswith("%"):
        display = answer_text[:-1].replace(",", "")
        decimals = len(display.split(".")[1]) if "." in display else 0
        tolerance = number("0.5") / (10 ** decimals) + number("0.00001")
        display_value = number(display)
        if abs(expected * 100 - display_value) <= tolerance:
            answer_unit = "ratio"
        elif abs(expected - display_value) <= tolerance:
            answer_unit = "percent"
        else:
            raise ValueError("answer_text_program_mismatch")
    evidence = collect_evidence(raw)
    gold_groups = set(qa["gold_inds"])
    steps = []
    for i, (op, operands) in enumerate(program):
        args = []
        for operand in operands:
            if operand.startswith("#"):
                args.append({"kind": "step", "ref": f"s{int(operand[1:])+1}"})
            elif operand.startswith("const_"):
                args.append({"kind": "constant", "value": render(number(operand))})
            else:
                n = number(operand)
                candidates = [key for key, e in evidence.items() if number(e["value"]) == n and e["group"] in gold_groups]
                if len(candidates) != 1:
                    raise ValueError("ambiguous_or_missing_gold_evidence")
                args.append({"kind": "evidence", "ref": candidates[0], "value": render(n)})
        steps.append({"id": f"s{i+1}", "op": op, "args": args, "result": render(outputs[i]),
                      "explanation": {"add": "将所列两项数值相加。", "subtract": "计算所列两项数值的差。", "multiply": "计算所列两项数值的乘积。", "divide": "用第一项除以第二项，求得对应比值。"}[op]})
    difficulty = "easy" if len(steps) == 1 else "medium" if len(steps) == 2 else "hard"
    kinds = {a["ref"][0] for s in steps for a in s["args"] if a["kind"] == "evidence"}
    return {"id": raw["id"], "report_id": raw["id"].split(".pdf")[0], "question": qa["question"],
            "table": raw["table"], "texts": raw.get("pre_text", []) + raw.get("post_text", []),
            "evidence": evidence, "difficulty": difficulty, "step_count": len(steps),
            "evidence_kind": "mixed" if len(kinds) > 1 else "text" if "x" in kinds else "table",
            "answer": {"value": str(qa["exe_ans"]), "unit": answer_unit},
            "reference": {"steps": steps, "final": {"value": render(outputs[-1]), "unit": answer_unit}},
            "source": {"dataset": "FinQA", "split": "train", "program": qa["program"],
                       "gold_inds": qa["gold_inds"], "answer_text": qa.get("answer", ""),
                       "alignment": "unique_numeric_match_within_gold_groups", "human_review": "pending"}}


def replay_claimed(trace):
    vals = {}
    for s in trace["steps"]:
        try:
            ns = [vals[a["ref"]] if a["kind"] == "step" else number(a["value"]) for a in s["args"]]
            s["result"] = render(calculate(s["op"], *ns))
            vals[s["id"]] = number(s["result"])
        except (ValueError, KeyError):
            return
    trace["final"] = {"value": trace["steps"][-1]["result"], "unit": trace["final"]["unit"]}


def controlled(problem, index):
    base = deepcopy(problem["reference"])
    items = [{"id": f"{problem['id']}::clean", "problem_id": problem["id"], "split": problem["split"],
              "source": "reference_derived", "trace": base,
              "label": {"process": "correct", "first_error": None, "type": None,
                        "method": "reference_program_conversion", "human_review": "pending"}}]
    # Each question has one local-verification error plus one harder semantic/CAIR case.
    t = deepcopy(base)
    first_evidence = next((i, j) for i, s in enumerate(t["steps"]) for j, a in enumerate(s["args"]) if a["kind"] == "evidence")
    pos, argindex = first_evidence
    kind = ["evidence_value", "arithmetic", "dependency"][index % 3]
    if kind == "evidence_value":
        arg = t["steps"][pos]["args"][argindex]
        arg["value"] = render(number(arg["value"]) + 1)
        replay_claimed(t)
    elif kind == "arithmetic":
        pos = index % len(t["steps"])
        t["steps"][pos]["result"] = render(number(t["steps"][pos]["result"]) + 1)
        vals = {s["id"]: number(s["result"]) for s in t["steps"][:pos+1]}
        for s in t["steps"][pos+1:]:
            try:
                ns = [vals[a["ref"]] if a["kind"] == "step" else number(a["value"]) for a in s["args"]]
                s["result"] = render(calculate(s["op"], *ns))
                vals[s["id"]] = number(s["result"])
            except ValueError:
                break
        t["final"]["value"] = t["steps"][-1]["result"]
    else:
        t["steps"][pos]["args"][argindex] = {"kind": "step", "ref": f"s{pos+1}"}
    items.append({"id": f"{problem['id']}::local", "problem_id": problem["id"], "split": problem["split"],
                  "source": "controlled_mutation", "trace": t,
                  "label": {"process": "incorrect", "first_error": f"s{pos+1}", "type": kind,
                            "method": "mutation_record", "human_review": "pending"},
                  "mutation": {"kind": kind, "before": base["steps"][pos], "after": t["steps"][pos]}})
    t = deepcopy(base)
    if index % 2 == 0:
        # A semantic error remains locally arithmetically valid; rules must abstain.
        pos = 0
        s = t["steps"][pos]
        old = s["op"]
        alternatives = [x for x in ("add", "subtract", "multiply") if x != old]
        for op in alternatives:
            s["op"] = op
            replay_claimed(t)
            if not close(number(t["final"]["value"]), number(base["final"]["value"])):
                break
        if close(number(t["final"]["value"]), number(base["final"]["value"])):
            raise ValueError("ineffective_mutation")
        kind = "formula"
        first = "s1"
    else:
        # Wrong arithmetic while keeping a correct final answer is an explicit CAIR case.
        pos = len(t["steps"]) - 1
        t["steps"][pos]["result"] = render(number(t["steps"][pos]["result"]) + 1)
        kind = "arithmetic"
        first = f"s{pos+1}"
    items.append({"id": f"{problem['id']}::challenge", "problem_id": problem["id"], "split": problem["split"],
                  "source": "controlled_mutation", "trace": t,
                  "label": {"process": "incorrect", "first_error": first, "type": kind,
                            "method": "mutation_record", "human_review": "pending"},
                  "mutation": {"kind": kind, "before": base["steps"][pos], "after": t["steps"][pos]}})
    return items


def build():
    raw = read_json(ROOT / "data/cache/dataset_train.json")
    candidates, exclusions = [], Counter()
    for r in raw:
        try:
            candidates.append((normalize(r), r))
        except (ValueError, KeyError, TypeError) as e:
            exclusions[str(e)] += 1
    candidates.sort(key=lambda p: hashlib.sha256(("fintrace-v1:" + p[0]["id"]).encode()).hexdigest())
    selected, original, reports, bands = [], [], set(), Counter()
    for problem, r in candidates:
        band = problem["difficulty"]
        if bands[band] >= 10 or problem["report_id"] in reports:
            continue
        # First 3 easy / 3 medium / 4 hard form the development set.
        quota = 4 if band == "hard" else 3
        problem["split"] = "dev" if bands[band] < quota else "test"
        bands[band] += 1
        selected.append(problem)
        original.append({k: r[k] for k in ["id", "pre_text", "post_text", "table"]} | {"qa": {k: r["qa"][k] for k in ["question", "program", "exe_ans", "gold_inds", "answer"]}})
        reports.add(problem["report_id"])
    if len(selected) != 30:
        raise ValueError(f"候选不足：{dict(bands)}")
    samples = [s for i, p in enumerate(selected) for s in controlled(p, i)]
    source = read_json(ROOT / "data/cache/download_manifest.json")
    manifest = {"source": source, "seed": "fintrace-v1", "problem_count": len(selected),
                "sample_count": len(samples), "bands": dict(bands), "splits": dict(Counter(p["split"] for p in selected)),
                "evidence_kinds": dict(Counter(p["evidence_kind"] for p in selected)),
                "eligible": len(candidates), "excluded": dict(exclusions), "human_review": "pending",
                "selection_rule": "four arithmetic operations, unique evidence match in gold groups, executable gold, distinct report, hash order"}
    write_json(ROOT / "data/finqa30.json", selected)
    write_json(ROOT / "data/controlled90.json", samples)
    write_json(ROOT / "data/source/finqa30_raw.json", original)
    write_json(ROOT / "data/manifest.json", manifest)
    license_text = (ROOT / "data/cache/LICENSE").read_text(encoding="utf-8")
    (ROOT / "data/source/FinQA-LICENSE.txt").write_text(license_text, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
