"""Prepare subtitles and transcript after locally encoding the narrated MP4."""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
work=ROOT/'demo/.work'
record=json.loads((work/'recording.json').read_text(encoding='utf-8'))
if not (ROOT/'demo/fintrace-demo.mp4').exists():
    raise SystemExit('Run node scripts/mux_demo.cjs first.')
def ts(seconds):
    ms=round(seconds*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
subs=[]
for i,s in enumerate(record['scenes'],1):
    subs.append(f'{i}\n{ts(s["start"])} --> {ts(s["start"]+s["duration"])}\n{s["narration"]}\n')
(ROOT/'demo/fintrace-demo.srt').write_text('\n'.join(subs),encoding='utf-8')
(ROOT/'demo/transcript.md').write_text('# FinTrace 演示旁白\n\n'+'\n\n'.join(f'## {i+1}. {s["title"]}\n\n{s["narration"]}' for i,s in enumerate(record['scenes']))+'\n',encoding='utf-8')
print(json.dumps({'video':str(ROOT/'demo/fintrace-demo.mp4'),'bytes':(ROOT/'demo/fintrace-demo.mp4').stat().st_size,'scenes':len(subs),'browser_errors':record['errors']},ensure_ascii=False))
