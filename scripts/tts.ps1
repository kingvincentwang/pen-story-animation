# Writes assets/voice/<panel name>.wav for every panel in story.json that has narration.
# Run from the project folder with Windows PowerShell 5.1:
#   powershell -ExecutionPolicy Bypass -File <skill>/scripts/tts.ps1 [-Voice Yating] [-Rate 0.95]
param([string]$Voice = 'Yating', [double]$Rate = 0.95)
$story = Get-Content story.json -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Force assets\voice | Out-Null
[void][Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
[void][Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(); $t.Result }
$s = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$all = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices
$v = $all | Where-Object { $_.DisplayName -match $Voice } | Select-Object -First 1
if (-not $v) { $v = $all | Where-Object { $_.Language -eq 'zh-TW' } | Select-Object -First 1 }
if (-not $v) { Write-Error 'No matching voice is installed.'; exit 1 }
$s.Voice = $v
$s.Options.SpeakingRate = $Rate
"voice: " + $v.DisplayName
foreach ($p in $story.panels) {
  if (-not $p.narration) { continue }
  $st = Await ($s.SynthesizeTextToStreamAsync($p.narration)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
  $r = New-Object Windows.Storage.Streams.DataReader($st)
  $n = [uint32]$st.Size
  [void](Await ($r.LoadAsync($n)) ([uint32]))
  $b = New-Object byte[] $n
  $r.ReadBytes($b)
  [IO.File]::WriteAllBytes((Join-Path (Get-Location) ("assets\voice\" + $p.name + ".wav")), $b)
  $p.name
}
