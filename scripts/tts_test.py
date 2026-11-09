import json, time, urllib.request
MODEL="Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
text="这是一次本机语音合成测速。我们正在验证，一台普通的 Mac 能不能在完全离线的条件下，稳定地生产中文播客节目。"
ins="成年男性，低沉清晰，标准普通话，语速适中，不要夸张的播音腔，像在认真讲一件事。"
body=json.dumps({"model":MODEL,"input":text,"instructions":ins,"response_format":"wav"}).encode()
req=urllib.request.Request("http://127.0.0.1:5091/v1/audio/speech",data=body,headers={"Content-Type":"application/json"})
t=time.perf_counter(); data=urllib.request.urlopen(req,timeout=300).read(); e=time.perf_counter()-t
open("audio/test.wav","wb").write(data)
print(f"chars={len(text)} bytes={len(data)} elapsed={e:.2f}s")
import wave
with wave.open("audio/test.wav") as w:
    print("rate",w.getframerate(),"channels",w.getnchannels(),"frames",w.getnframes(),"dur",w.getnframes()/w.getframerate())
