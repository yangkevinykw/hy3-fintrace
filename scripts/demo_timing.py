"""Measure local WAV narration to synchronize the screen recording."""
import json
from pathlib import Path
import wave
root=Path(__file__).resolve().parents[1]
scenes=json.loads((root/'demo/scenes.json').read_text(encoding='utf-8'))
for index,scene in enumerate(scenes):
    with wave.open(str(root/'demo/.work'/f'{index:02}.wav')) as audio:
        scene['duration']=audio.getnframes()/audio.getframerate()
(root/'demo/.work/scenes.json').write_text(json.dumps(scenes,ensure_ascii=False,indent=2),encoding='utf-8')
print('Narration duration:',round(sum(s['duration'] for s in scenes),2),'seconds')
