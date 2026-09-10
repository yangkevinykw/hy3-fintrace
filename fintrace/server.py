"""Local-only web workbench. No third-party server dependency or external assets."""
from __future__ import annotations
import hashlib
import json
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .storage import ROOT, read_json, write_json, load_dataset
from .evaluator import evaluate
from .model import public_config, public_problem, solve, new_run_id, judge, combine


def create_server(port=8765, review_root=None):
    review_root = review_root or ROOT / "runs/reviews"
    problems = {p["id"]: p for p in load_dataset()}
    samples = read_json(ROOT / "data/controlled90.json")
    sample_map = {s["id"]: s for s in samples}
    review_map = {hashlib.sha256(("blind-v1:" + s["id"]).encode()).hexdigest()[:16]: s for s in samples}
    token, lock = secrets.token_urlsafe(32), threading.Lock()
    static = ROOT / "fintrace/web"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, obj, status=200):
            payload = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            return self.headers.get("Host", "") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self.valid_host():
                return self.send({"error": "Host not allowed"}, 403)
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/api/bootstrap":
                return self.send({"token": token, "config": public_config(), "manifest": read_json(ROOT / "data/manifest.json"),
                                  "cases": [{"id": s["id"], "problem_id": s["problem_id"], "source": s["source"], "split": s["split"],
                                             "difficulty": problems[s["problem_id"]]["difficulty"], "question": problems[s["problem_id"]]["question"]} for s in samples]})
            if parsed.path == "/api/case":
                sample = sample_map.get(query.get("id", [""])[0])
                if sample is None:
                    return self.send({"error": "Unknown case"}, 404)
                p = problems[sample["problem_id"]]
                return self.send({"problem": p, "sample": sample, "evaluation": evaluate(p, sample["trace"])})
            if parsed.path == "/api/summary":
                report = ROOT / "runs/offline/summary.json"
                return self.send(read_json(report) if report.exists() else {"pending": True})
            if parsed.path == "/api/review":
                keys = sorted(review_map)
                key = query.get("id", [keys[0]])[0]
                sample = review_map.get(key)
                if sample is None:
                    return self.send({"error": "Unknown review"}, 404)
                path = review_root / f"{key}.json"
                # No evaluator output, mutation labels, answer or reference before submission.
                data = {"ids": keys, "id": key, "problem": public_problem(problems[sample["problem_id"]]), "trace": sample["trace"],
                        "saved": read_json(path) if path.exists() else None}
                if path.exists():
                    data["evaluation"] = evaluate(problems[sample["problem_id"]], sample["trace"])
                return self.send(data)
            files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
            if parsed.path not in files:
                return self.send({"error": "Not found"}, 404)
            name, content_type = files[parsed.path]
            data = (static / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self.valid_host() or self.headers.get("X-FinTrace-Token") != token:
                return self.send({"error": "请求来源校验失败，请刷新页面。"}, 403)
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
                return self.send({"error": "Origin not allowed"}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 500_000:
                    raise ValueError("请求过大或为空")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("需要 JSON 对象")
                if self.path == "/api/review":
                    key = data.get("id")
                    sample = review_map.get(key)
                    if sample is None or data.get("process") not in ("correct", "incorrect", "uncertain"):
                        raise ValueError("复核结论格式无效")
                    if not isinstance(data.get("reviewer"), str) or not data["reviewer"].strip() or not isinstance(data.get("reason"), str) or not data["reason"].strip():
                        raise ValueError("请填写复核人和判断依据")
                    step = data.get("first_error") or None
                    valid = {s["id"] for s in sample["trace"]["steps"]} | {None, "final"}
                    if step not in valid or (data["process"] != "incorrect" and step is not None):
                        raise ValueError("首错位置与结论不一致")
                    path = review_root / f"{key}.json"
                    with lock:
                        if path.exists():
                            raise ValueError("初始盲评已提交，不能覆盖原始记录")
                        record = {"id": key, "sample_id": sample["id"], "reviewer": data["reviewer"].strip()[:100],
                                  "process": data["process"], "first_error": step, "reason": data["reason"][:5000],
                                  "created_at": datetime.now(timezone.utc).isoformat(), "protocol": "ui_verdict_hidden_before_submit"}
                        write_json(path, record)
                    return self.send({"saved": True})
                p = problems.get(data.get("problem_id"))
                if p is None:
                    raise ValueError("未知题目")
                if self.path == "/api/evaluate":
                    return self.send({"evaluation": evaluate(p, data.get("trace"))})
                if self.path == "/api/solve":
                    if not public_config()["ready"]:
                        return self.send({"error": "Hy3 尚未配置。请填写项目中的 .env 后重试。"}, 409)
                    if not lock.acquire(blocking=False):
                        return self.send({"error": "已有调用正在运行，请稍候。"}, 409)
                    try:
                        run_id = new_run_id(p["id"])
                        folder = ROOT / "runs/live" / run_id
                        response = solve(p, folder)
                        if response["status"] != "complete":
                            return self.send({"error": response.get("message", "模型调用失败"), "status": response["status"], "run_id": run_id}, 502)
                        trace = response["output"]
                        result = evaluate(p, trace)
                        if data.get("semantic") is True:
                            result = combine(result, judge(p, trace, folder))
                        write_json(folder / "result.json", {"problem_id": p["id"], "source": "hy3_live", "trace": trace, "evaluation": result})
                        return self.send({"trace": trace, "evaluation": result, "run_id": run_id})
                    finally:
                        lock.release()
                return self.send({"error": "Not found"}, 404)
            except (ValueError, TypeError, KeyError, OverflowError):
                return self.send({"error": "请求字段或数值无效，请检查输入。"}, 400)
            except OSError:
                return self.send({"error": "本地文件读写失败。"}, 500)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port=8765):
    server = create_server(port)
    print(f"FinTrace 工作台：http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
