"""Small dependency-free validation of the public trace protocol."""
from .core import OPS, number


def validate_trace(trace):
    errors=[]
    if not isinstance(trace,dict):
        return ["解答必须是对象"]
    steps=trace.get("steps")
    if not isinstance(steps,list) or not 1<=len(steps)<=24:
        return ["steps 需包含 1–24 个步骤"]
    for i,s in enumerate(steps,1):
        if not isinstance(s,dict):
            errors.append(f"s{i} 不是对象")
            continue
        if s.get("id")!=f"s{i}":
            errors.append(f"s{i} 编号无效")
        if not isinstance(s.get("op"),str) or s["op"] not in OPS:
            errors.append(f"s{i} 运算符无效")
        args=s.get("args")
        if not isinstance(args,list) or len(args)!=2:
            errors.append(f"s{i} 必须有两个操作数")
        else:
            for a in args:
                if not isinstance(a,dict) or not isinstance(a.get("kind"),str) or a["kind"] not in ("evidence","step","constant"):
                    errors.append(f"s{i} 操作数格式无效")
                    continue
                if a["kind"] in ("evidence","step") and not isinstance(a.get("ref"),str):
                    errors.append(f"s{i} 引用需为字符串")
                if a["kind"]!="step":
                    try: number(a.get("value"))
                    except ValueError: errors.append(f"s{i} 操作数值无效")
        try: number(s.get("result"))
        except ValueError: errors.append(f"s{i} 结果无效")
    final=trace.get("final")
    if not isinstance(final,dict):
        errors.append("缺少 final 对象")
    else:
        if final.get("unit") not in ("number","ratio","percent"):
            errors.append("答案单位无效")
        try: number(final.get("value"))
        except ValueError: errors.append("答案数值无效")
    return errors
