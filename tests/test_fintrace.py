import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fintrace.core import number, calculate, execute_program, render
from fintrace.evaluator import evaluate
from fintrace.model import public_problem, parse_json_output, combine, request_model
from fintrace.storage import ROOT, load_dataset, read_json
from fintrace.benchmark import metrics


def evidence(ref, value):
    return {"kind": "evidence", "ref": ref, "value": str(value)}


def previous(ref):
    return {"kind": "step", "ref": ref}


def fixed(value):
    return {"kind": "constant", "value": str(value)}


def step(id, op, args, result):
    return {"id": id, "op": op, "args": args, "result": str(result), "explanation": "依据财务数据计算。"}


def fixture():
    trace = {"steps": [step("s1", "subtract", [evidence("new",120), evidence("old",100)],20),
                       step("s2", "divide", [previous("s1"), evidence("old",100)],"0.2")],
             "final": {"value": "0.2", "unit": "ratio"}}
    p = {"id":"fixture", "question":"Revenue grows from 100 to 120. What is the growth rate?",
         "table":[["year","revenue"],["old","100"],["new","120"]],"texts":[],
         "evidence":{ref:{"value":str(n),"text":ref} for ref,n in [("new",120),("old",100),("irrelevant",120)]},
         "answer":{"value":"0.2","unit":"ratio"}, "reference": deepcopy(trace)}
    return p,trace


class ArithmeticTests(unittest.TestCase):
    def test_percent_and_accounting(self):
        self.assertEqual(number("23.6%"), number("0.236"))
        self.assertEqual(number("($ 1,250)"), number("-1250"))

    def test_malicious_and_nonfinite(self):
        for text in ["__import__('os')", "NaN", "Infinity", True, {}, "1e9999"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                number(text)

    def test_division_and_forward_refs(self):
        with self.assertRaises(ValueError):
            calculate("divide",number(2),number(0))
        with self.assertRaises(ValueError):
            execute_program("add(#0, 1)")

    def test_precision(self):
        self.assertEqual(execute_program("subtract(0.3, 0.2)")[0], number("0.1"))
        self.assertAlmostEqual(float(number(render(number(1)/number(3)))),1/3)


class EvaluatorTests(unittest.TestCase):
    def test_correct_percent(self):
        p,t=fixture(); r=evaluate(p,t)
        self.assertEqual(r["process"],"correct")
        self.assertTrue(r["answer_correct"])

    def test_explicit_percent_conversion_matches_ratio_reference(self):
        p,t=fixture()
        t["steps"].append(step("s3","multiply",[previous("s2"),fixed(100)],20))
        t["final"]={"value":"20","unit":"percent"}
        r=evaluate(p,t)
        self.assertEqual(r["process"],"correct")
        self.assertTrue(r["answer_correct"])
        p["reference"]=deepcopy(t)
        p["answer"]={"value":"20","unit":"percent"}
        t["steps"].pop();t["final"]={"value":"0.2","unit":"ratio"}
        r=evaluate(p,t)
        self.assertEqual(r["process"],"correct")
        self.assertTrue(r["answer_correct"])

    def test_equivalent_alternative_is_accepted(self):
        p,t=fixture()
        t["steps"]=[step("s1","divide",[evidence("new",120),evidence("old",100)],"1.2"),
                    step("s2","subtract",[previous("s1"),fixed(1)],"0.2")]
        self.assertEqual(evaluate(p,t)["process"],"correct")

    def test_wrong_formula_is_not_mechanically_condemned(self):
        p,t=fixture();t["steps"][1]["args"][1]=evidence("new",120)
        t["steps"][1]["result"]=render(number(20)/number(120))
        t["final"]={"value":t["steps"][1]["result"],"unit":"ratio"}
        r=evaluate(p,t)
        self.assertEqual(r["process"],"uncertain")
        self.assertFalse(r["answer_correct"])
        self.assertIsNone(r["first_error"])

    def test_wrong_evidence_with_same_number_is_not_proven_valid(self):
        p,t=fixture();t["steps"][0]["args"][0]["ref"]="irrelevant"
        r=evaluate(p,t)
        self.assertTrue(r["answer_correct"])
        self.assertEqual(r["process"],"uncertain")

    def test_first_error_and_propagation(self):
        p,t=fixture();t["steps"][0]["result"]="21";t["steps"][1]["result"]="0.21";t["final"]["value"]="0.21"
        r=evaluate(p,t)
        self.assertEqual(r["first_error"]["step"],"s1")
        self.assertEqual(r["steps"][1]["status"],"affected")
        self.assertEqual(r["steps"][1]["affected_by"],["s1"])
        self.assertEqual(len([f for f in r["findings"] if f["type"]=="arithmetic"]),1)

    def test_correct_answer_does_not_hide_arithmetic_error(self):
        p,t=fixture();t["steps"][1]["result"]="0.3"
        r=evaluate(p,t)
        self.assertTrue(r["correct_answer_invalid_process"])
        self.assertEqual(r["first_error"]["step"],"s2")

    def test_missing_evidence_and_dependency(self):
        for kind,arg in [("evidence_missing",evidence("absent",120)),("dependency",previous("s2"))]:
            p,t=fixture();t["steps"][0]["args"][0]=arg
            self.assertEqual(evaluate(p,t)["first_error"]["type"],kind)

    def test_final_unit_not_silently_guessed(self):
        p,t=fixture();t["final"]["value"]="20"
        r=evaluate(p,t)
        self.assertFalse(r["answer_correct"])
        self.assertEqual(r["first_error"]["type"],"answer_consistency")

    def test_mutation_labels_cannot_change_verdict(self):
        p,t=fixture();a=evaluate(p,t)
        t.update({"gold_label":"incorrect","first_error":"s1","mutation":{"type":"arithmetic"}})
        self.assertEqual(a,evaluate(p,t))

    def test_missing_and_malformed_traces(self):
        p,t=fixture()
        for trace in [None,[],{}, {"steps":[]}, {"steps":[None]}, {"steps":[{"id":"s1","op":"add","args":[None,None]}]}]:
            with self.subTest(trace=trace):
                self.assertEqual(evaluate(p,trace)["process"],"incorrect")


class DataTests(unittest.TestCase):
    def test_percentage_source_scale_and_contradiction(self):
        from fintrace.dataset import normalize
        raw=deepcopy(read_json(ROOT/'data/source/finqa30_raw.json')[0])
        raw['qa']['exe_ans']=98.18
        raw['qa']['answer']='98.18%'
        p=normalize(raw)
        self.assertEqual(p['answer']['unit'],'percent')
        self.assertTrue(evaluate(p,p['reference'])['answer_correct'])
        raw['qa']['answer']='95.04%'
        with self.assertRaisesRegex(ValueError,'answer_text_program_mismatch'):
            normalize(raw)

    def test_split_sizes_and_report_isolation(self):
        ps=load_dataset()
        self.assertEqual(len(ps),30)
        self.assertEqual(sum(p["split"]=="dev" for p in ps),10)
        dev={p["report_id"] for p in ps if p["split"]=="dev"}
        test={p["report_id"] for p in ps if p["split"]=="test"}
        self.assertFalse(dev & test)
        sample=read_json(ROOT/"data/controlled90.json")
        self.assertEqual(len(sample),90)
        split={p["id"]:p["split"] for p in ps}
        self.assertTrue(all(s["split"]==split[s["problem_id"]] for s in sample))

    def test_model_input_excludes_reference_and_labels(self):
        p=load_dataset()[0];payload=public_problem(p)
        for key in ["answer","reference","source","label","split"]:
            self.assertNotIn(key,payload)

    def test_metric_denominators_include_abstentions(self):
        rows=[{"label":{"process":"incorrect","first_error":"s1","type":"formula"},
               "evaluation":{"process":"uncertain","first_error":None,"answer_correct":False,"correct_answer_invalid_process":False}}]
        result=metrics(rows)
        self.assertEqual(result["detection"],{"numerator":0,"denominator":1,"rate":0.0})
        self.assertEqual(result["localization"]["denominator"],1)
        self.assertIsNone(result["false_positive"]["rate"])


class ModelTests(unittest.TestCase):
    def test_json_parser(self):
        self.assertEqual(parse_json_output('```json\n{"steps":[]}\n```'),{"steps":[]})
        for s in ['{"x":NaN}','[1,2]','not json',None]:
            with self.assertRaises(ValueError):
                parse_json_output(s)

    def test_failed_judge_is_not_success(self):
        p,t=fixture()
        r=combine(evaluate(p,t),{"status":"request_failed"})
        self.assertEqual(r["process"],"uncertain")

    def test_hard_evidence_overrides_judge(self):
        p,t=fixture();t["steps"][0]["result"]="999"
        r=combine(evaluate(p,t),{"status":"complete","output":{"process":"correct"}})
        self.assertEqual(r["process"],"incorrect")
        self.assertTrue(r["judge_conflict"])

    def test_earlier_semantic_error_preserves_later_hard_evidence(self):
        p,t=fixture();t["steps"][1]["result"]="999"
        r=combine(evaluate(p,t),{"status":"complete","output":{"process":"incorrect","first_error_step":"s1","error_type":"formula","reason":"Test-only earlier diagnosis"}})
        self.assertEqual(r["first_error"]["step"],"s1")
        self.assertEqual(r["localization"],"judge_estimate")
        self.assertTrue(any(f["step"]=="s2" for f in r["findings"]))

    def test_invalid_trace_schema(self):
        from fintrace.schema import validate_trace
        self.assertTrue(validate_trace({"steps":[{"op":{},"args":[]}]}))
        p,t=fixture()
        self.assertFalse(validate_trace(t))

    def test_truncated_transport_keeps_raw_without_valid_output(self):
        cfg={"HY3_API_KEY":"test-secret-token", "HY3_BASE_URL":"https://example.test/v1","HY3_MODEL":"test"}
        raw={"choices":[{"finish_reason":"length","message":{"content":"test-secret-token"}}]}
        with tempfile.TemporaryDirectory() as d, patch('fintrace.model.config',return_value=(cfg,True)), patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(raw).encode()
            r=request_model([],Path(d),"solver")
            self.assertEqual(r["status"],"truncated")
            self.assertNotIn("output",r)
            content=(Path(d)/'solver_response_0.json').read_text(encoding='utf-8')
            self.assertIn('[REDACTED]',content)
            self.assertNotIn('test-secret-token',content)

    def test_transport_missing_credentials_no_artifact(self):
        with tempfile.TemporaryDirectory() as d, patch('fintrace.model.config',return_value=({},False)):
            result=request_model([],Path(d)/"run","solver")
            self.assertEqual(result["status"],"not_configured")
            self.assertFalse((Path(d)/"run").exists())

    def test_transport_timeout_and_secret_redaction(self):
        cfg={"HY3_API_KEY":"test-secret-token", "HY3_BASE_URL":"https://example.test/v1","HY3_MODEL":"test"}
        with tempfile.TemporaryDirectory() as d, patch('fintrace.model.config',return_value=(cfg,True)), patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError("test-secret-token")
            r=request_model([],Path(d),"solver")
            self.assertEqual(r["status"],"request_failed")
            self.assertEqual(opener.return_value.open.call_count,2)
            for file in Path(d).iterdir():
                self.assertNotIn("test-secret-token",file.read_text(encoding="utf-8"))


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fintrace.server import create_server
        cls.review_temp=tempfile.TemporaryDirectory()
        cls.server=create_server(0,review_root=Path(cls.review_temp.name))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_port}"
        cls.boot=cls.get('/api/bootstrap')

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.review_temp.cleanup()

    @classmethod
    def get(cls,path):
        with urllib.request.urlopen(cls.base+path) as r:
            return json.load(r)

    def test_no_token_write_rejected(self):
        req=urllib.request.Request(self.base+'/api/evaluate',data=b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code,403)
        cm.exception.close()

    def test_blind_review_hides_evaluator_and_gold(self):
        result=self.get('/api/review')
        self.assertNotIn('evaluation',result)
        for key in ['answer','reference','source']:
            self.assertNotIn(key,result['problem'])
        self.assertIsNone(result['saved'])

    def test_endpoint_uses_same_evaluator(self):
        p=load_dataset()[0]
        data=json.dumps({'problem_id':p['id'],'trace':p['reference']}).encode()
        req=urllib.request.Request(self.base+'/api/evaluate',data=data,headers={'Content-Type':'application/json','X-FinTrace-Token':self.boot['token']})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(json.load(r)['evaluation'],evaluate(p,p['reference']))

    def test_cross_origin_and_host_rejected(self):
        for extra in [{'Origin':'https://evil.test'},{'Host':'evil.test'}]:
            req=urllib.request.Request(self.base+'/api/evaluate',data=b'{}',headers={'Content-Type':'application/json','X-FinTrace-Token':self.boot['token'],**extra})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code,403)
            cm.exception.close()

    def test_review_write_is_immutable_and_reveal_follows_save(self):
        listing=self.get('/api/review')
        key=listing['ids'][-1]
        payload={'id':key,'reviewer':'automated-test-only','process':'uncertain','first_error':None,'reason':'Temporary test record, not a human label'}
        def req():
            return urllib.request.Request(self.base+'/api/review',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-FinTrace-Token':self.boot['token']})
        with urllib.request.urlopen(req()) as response:
            self.assertTrue(json.load(response)['saved'])
        saved=self.get('/api/review?id='+key)
        self.assertIn('evaluation',saved)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req())
        self.assertEqual(cm.exception.code,400)
        cm.exception.close()


if __name__=='__main__':
    unittest.main()
