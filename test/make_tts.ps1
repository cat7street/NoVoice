param([string]$Out = "D:\NoVoice\test\speech.wav")
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($Out, $fmt)
$text = "大家好，欢迎收看本期节目。今天我们来讲一讲人工智能是如何把歌曲里的人声分离出来的。" +
        "这个技术叫做音源分离，它可以把一段混合音频拆分成人声、鼓、贝斯和其他乐器。" +
        "分离完成之后，我们把人声去掉，剩下的伴奏再和原来的视频画面合在一起，就得到了没有解说声音的视频。" +
        "谢谢大家观看，我们下期再见。"
try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female, [System.Speech.Synthesis.VoiceAge]::Adult, 0, [Globalization.CultureInfo]::new("zh-CN")) } catch {}
$s.Speak($text)
$s.Dispose()
Write-Host "OK $Out"
