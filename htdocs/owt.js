var owt_protocol = 'ws://';
if(window.location.toString().indexOf('https://') == 0){
  owt_protocol = 'wss://';
}
owt_url1=owt_protocol+window.location.href.split("://")[1]
owt_lastslash = owt_url1.lastIndexOf('/');
owt_firstslash= owt_url1.indexOf('/',6);
owt_url2=owt_url1.substr(0,owt_firstslash)
//owt_url2=owt_url1.substr(0,owt_lastslash)
owt_ws_url=owt_url2+"/tx/ws/";
owt_button_orig=""
var owt_webSocket;
var owt_mediaRecorder
function owt_start_ws(start_audio) {
  owt_webSocket = new WebSocket(owt_ws_url);
  owt_webSocket.binaryType = 'blob';

  owt_webSocket.onmessage= function (event) {
    console.log('Message from server ', event.data);
    owt_make_msg(event.data);
  }
  owt_webSocket.onclose =function (event) {
    console.log('ws closed :(', event.data);
    owt_make_button_orig();
    owt_make_msg('TX connection closed!');
    owt_destroy_ws()
  }
  if(start_audio) {
    //owt_webSocket.onopen =owt_start_audio();
    if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
      mimeType="audio/ogg;codecs=opus";
    } else  {
      mimeType="audio/webm;codecs=opus";
    }	    

  //function owt_start_audio(){
    owt_webSocket.onopen = event => {
      console.log("[open] Audio Node-RED websocket connection established");
      navigator.mediaDevices
        .getUserMedia({ audio: true, video: false, channelCount: 1, sampleRate: 12000, sampleSize: 16  })
        .then(stream => {
          owt_mediaRecorder = new MediaRecorder(stream, {
	    //audioBitsPerSecond : 128000,
            audioBitsPerSecond : 64000,
            //mimeType: 'audio/webm;codecs=opus',
            //mimeType: 'audio/ogg;codecs=opus',
            mimeType: mimeType,
          });
          owt_mediaRecorder.addEventListener('dataavailable', event => {
            if (event.data.size > 0) {
              //console.log(event.data.length)
              owt_webSocket.send(event.data);
            }
          });
          owt_mediaRecorder.start(100);
        });
    }
  }
}
function owt_stop_ws() {
  track=owt_mediaRecorder.stream.getAudioTracks()
  track.forEach(function(track) { track.stop(); });

  owt_webSocket.close()
  owt_make_button_orig()
}
function owt_destroy_ws() {
  if (typeof owt_mediaRecorder === "object" ) {
    a=owt_mediaRecorder.stream.getAudioTracks();
    owt_mediaRecorder.stream.removeTrack(a[0]);
    owt_mediaRecorder.removeEventListener('dataavilable',Element)
    owt_mediaRecorder.stop()
    owt_mediaRecorder=0
    console.log("audio destroyed")
  }
  owt_webSocket=0;
  console.log("ws destroyed")
}
function owt_make_button_running() {
  //PTT button, close link
  document.getElementById('owt_button').innerHTML="<div class='openwebrx-button' id='owt_ptt' onmousedown='owt_ptt_on();' onmouseup='owt_ptt_off();' ontouchstart='owt_ptt_on();' ontouchend='owt_ptt_off();' >PTT</div> <a onclick='owt_stop_ws();' >disconnect</a>"
}
function owt_make_button_orig() {
  //connect button from variable
  document.getElementById('owt_button').innerHTML=owt_button_orig
}
function owt_make_msg(data) {
//if data contains config:, status: => ignore
//else if containts msg: => split and print
  document.getElementById('owt_msg').innerHTML=""
//else print
}
function owt_start() {
  //owt_vumeter()
  owt_button_orig= document.getElementById('owt_button').innerHTML
  owt_start_ws(1);
  //owt_start_audio();
  owt_make_button_running();
}

function owt_ptt_on() {
  mute=false;
  toggleMute();
  owt_webSocket.send("SET:PTT=1")
  document.getElementById('owt_ptt').style.background="#fff"
  document.getElementById('owt_ptt').style.color="#f00"
}
function owt_ptt_off() {
  mute=true;
  toggleMute();
  owt_webSocket.send("SET:PTT=0")
  document.getElementById('owt_ptt').style.background="#f00"
  document.getElementById('owt_ptt').style.color="#fff"
}
//keypress
//keydown
//keyup
//left  37
//right 39
//up    38
//down  40
document.addEventListener('keydown', function(e) {
  var keynum = e.keyCode || e.which;
  console.log(keynum)
  if(keynum == 32) {
    owt_ptt_on()
  }
});
document.addEventListener('keyup', function(e) {
  var keynum = e.keyCode || e.which;
  console.log("up"+keynum)
  if(keynum == 32) {
    owt_ptt_off()
  }
});
document.addEventListener('keypress', function(e) {
  var keynum = e.keyCode || e.which;
  console.log("press"+keynum)
//  if(keynum == 32) {
//    owt_ptt_off()
//  }
});

//https://stackoverflow.com/questions/33322681/checking-microphone-volume-in-javascript
function owt_vumeter() {
  document.getElementById('owt_pids').innerHTML=`
		  <div class='owt_pid'></div>
		  <div class='owt_pid'></div>
		  <div class='owt_pid'></div>
		  <div class='owt_pid'></div>
		  <div class='owt_pid'></div>
		  <div class='owt_pid'></div>`;

  navigator.mediaDevices.getUserMedia({
    audio: true,
    video: false,
    })
    .then(function(stream) {
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      const microphone = audioContext.createMediaStreamSource(stream);
      const scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);
      analyser.smoothingTimeConstant = 0.8;
      analyser.fftSize = 1024;

      microphone.connect(analyser);
      analyser.connect(scriptProcessor);
      scriptProcessor.connect(audioContext.destination);
      scriptProcessor.onaudioprocess = function() {
        const array = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(array);
        const arraySum = array.reduce((a, value) => a + value, 0);
        const average = arraySum / array.length;
        //console.log(Math.round(average));
        owt_colorPids(average);
      };
    })
    .catch(function(err) {
      /* handle the error */
      console.error(err);
    });
}                   
function owt_colorPids(vol) { 
  //console.log('vu'+vol);
  const allPids = [...document.querySelectorAll('.owt_pid')];
  const numberOfPidsToColor = Math.round(vol / 20);
  const pidsToColor = allPids.slice(0, numberOfPidsToColor);
  for (const pid of allPids) {
    pid.style.backgroundColor = "#e6e7e8";
  }
  for (const pid of pidsToColor) {
    //console.log(pid[i]);
    pid.style.backgroundColor = "#00ce00";
  }
}



//TODO
//  //on websocket rx
//  display MSG (on air, problem [rigctl, high-swr, other user took over], ....)
//  on websocket close => display msg
//  fkt:
//      display msg
//      get parameters from ws-rx and update gui if gui present
//      send parameters from gui to ws (relay shift, ctcss, power, external IO)

