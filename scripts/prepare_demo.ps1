$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path $PSScriptRoot -Parent
$demoWork = Join-Path $demoRoot 'demo/.work'
New-Item -ItemType Directory -Path $demoWork -Force | Out-Null
Add-Type -AssemblyName System.Speech
$demoSynth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$demoSynth.SelectVoice('Microsoft Huihui Desktop')
$demoSynth.Rate = 2
$demoScenes = Get-Content (Join-Path $demoRoot 'demo/scenes.json') -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    for ($demoIndex = 0; $demoIndex -lt $demoScenes.Count; $demoIndex++) {
        $demoSynth.SetOutputToWaveFile((Join-Path $demoWork ('{0:D2}.wav' -f $demoIndex)))
        $demoSynth.Speak($demoScenes[$demoIndex].narration)
        $demoSynth.SetOutputToNull()
    }
} finally { $demoSynth.Dispose() }
Write-Output 'Prepared offline Chinese narration for eight scenes.'
python (Join-Path $PSScriptRoot 'demo_timing.py')
