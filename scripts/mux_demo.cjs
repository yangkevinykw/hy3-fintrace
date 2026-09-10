/* Encode a narrated MP4 locally with Chromium's native MediaRecorder. */
const fs=require('fs'),path=require('path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),work=path.join(root,'demo','.work');
(async()=>{
 const record=JSON.parse(fs.readFileSync(path.join(work,'recording.json'),'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:process.env.DEMO_CHROMIUM,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage();
 await page.exposeFunction('reportProgress',s=>console.log(s));
 const result=await page.evaluate(async({videoData,scenes})=>{
   const video=document.createElement('video');video.muted=true;video.playsInline=true;video.src='data:video/webm;base64,'+videoData;document.body.appendChild(video);
   await new Promise((resolve,reject)=>{video.onloadeddata=resolve;video.onerror=()=>reject(new Error('Source video decode failed'))});
   const audio=new AudioContext();const destination=audio.createMediaStreamDestination();
   const buffers=await Promise.all(scenes.map(async s=>audio.decodeAudioData(Uint8Array.from(atob(s.wav),c=>c.charCodeAt(0)).buffer)));
   await audio.resume();
   const source=video.captureStream();
   await video.play();video.pause();video.currentTime=0;
   await new Promise(r=>setTimeout(r,100));
   const stream=new MediaStream([...source.getVideoTracks(),...destination.stream.getAudioTracks()]);
   const mime='video/mp4;codecs=avc1.42001E,mp4a.40.2';
   const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:1800000,audioBitsPerSecond:128000});
   const chunks=[];recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
   const stopped=new Promise((resolve,reject)=>{recorder.onstop=resolve;recorder.onerror=e=>reject(new Error(e.error?.message||'Encoding failed'))});
   recorder.start(1000);
   const start=audio.currentTime;
   scenes.forEach((s,i)=>{const node=audio.createBufferSource();node.buffer=buffers[i];node.connect(destination);node.start(start+s.start)});
   const ended=new Promise(resolve=>video.onended=resolve);
   const timer=setInterval(()=>window.reportProgress('Encoding '+video.currentTime.toFixed(1)+' / '+video.duration.toFixed(1)+' seconds'),15000);
   await video.play();await ended;clearInterval(timer);await new Promise(r=>setTimeout(r,200));recorder.stop();await stopped;
   const blob=new Blob(chunks,{type:'video/mp4'});
   const data=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(blob)});
   const meta={duration:video.duration,width:video.videoWidth,height:video.videoHeight,audioTracks:stream.getAudioTracks().length,mime,bytes:blob.size};
   await audio.close();return {data,meta};
 },{videoData:fs.readFileSync(record.videoPath).toString('base64'),scenes:record.scenes.map((s,i)=>({...s,wav:fs.readFileSync(path.join(work,`${String(i).padStart(2,'0')}.wav`)).toString('base64')}))});
 fs.writeFileSync(path.join(root,'demo','fintrace-demo.mp4'),Buffer.from(result.data,'base64'));
 fs.writeFileSync(path.join(work,'video-metadata.json'),JSON.stringify(result.meta,null,2));
 await browser.close();console.log(JSON.stringify(result.meta));
})().catch(e=>{console.error(e);process.exit(1)});
