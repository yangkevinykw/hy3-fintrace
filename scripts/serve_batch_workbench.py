"""Add fixed read-only experiment endpoints without changing frozen evaluator code."""
from pathlib import Path
import sys
from urllib.parse import urlparse, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fintrace.storage import ROOT, read_json
from fintrace.server import create_server

def create_batch_server(port=8765):
    server=create_server(port)
    original=server.RequestHandlerClass
    class BatchHandler(original):
        def do_GET(self):
            if not self.valid_host():
                return self.send({'error':'Host not allowed'},403)
            url=urlparse(self.path)
            version=parse_qs(url.query).get('version',['batch-v2'])[0]
            if version not in ('batch-v1','batch-v2'):
                return self.send({'error':'Unknown experiment version'},400)
            report=ROOT/'runs/experiments'/version
            if version=='batch-v2' and not report.exists():
                report=ROOT/'runs/experiments/batch-v1'
            if url.path=='/api/summary':
                p=report/'rules_summary.json'
                if p.exists():
                    return self.send(read_json(p))
            if url.path=='/api/experiment':
                p=report/'summary.json'
                return self.send(read_json(p) if p.exists() else {'pending':True})
            if url.path=='/api/experiment/case':
                p=report/'generation_results.json'
                identity=parse_qs(url.query).get('id',[''])[0]
                if p.exists():
                    row=next((r for r in read_json(p) if r['problem_id']==identity),None)
                    if row is not None:
                        return self.send(row)
                return self.send({'error':'No saved experiment result for this case'},404)
            return super().do_GET()
    server.RequestHandlerClass=BatchHandler
    return server

if __name__=='__main__':
    server=create_batch_server()
    print(f'FinTrace: http://127.0.0.1:{server.server_port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
