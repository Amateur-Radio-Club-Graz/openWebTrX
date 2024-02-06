# openWebTrX
Web Bases Ham Radio remote station  
![block diagram of setup](/grafics/ptt2.png)  

Using SDR based [simple_openwebrx](https://github.com/oe2lsp/simple_openwebrx), and accessing the pc microphone over the browser for a return channel.

The SDR is used for receiving only like traditional WebSDRs. 
As transmitter an old style stransmitter is used that can be controlled using some kind of CAT interface. With this combination the best out of two worlds is combined and available hardware can be reused.
For TX, the return channel compressed audio is sent over websocket. By using websocket in both direction this way only one TCP port is used and it can easyly be secured. 

Diagram of the whole software/hardware setup:

![block diagram of setup](/grafics/openwebtx.png)



## dependencies, requirements

 - libhamlib-utils (for rigctl)
 - ffmpeg 
 - [simple_openwebrx](https://github.com/oe2lsp/simple_openwebrx)
     - python3-psutil
     - python3-ẃebsockets

 - [csdr_s](https://github.com/oe2lsp/csdr)
     - libfftw3-dev

- nginx
- apache2-utils
- (this repo)

## installation
#### openwebrx
  install [simple_openwebrx](https://github.com/oe2lsp/simple_openwebrx) to selected destination 
  start simple openwebrx by hand to check if everything is working

#### edit config.py of simple openwebrx and set following 2 parameters:
```python
receiver_html_head="""<script src='/tx/owt.js'></script>
  <link rel='stylesheet' type='text/css' href='/tx/owt.css'>"""
 
receiver_html_content="""<div id='owt_head'>  <div id='owt_button'>
   <div class='openwebrx-button' onclick='owt_start();' >connect TX</div></div>
   <div id='owt_pids'></div></div><div id='owt_msg'></div>"""
 ```
 add custrom stuff to frontent like chat, and keep compatible to upstream code
 
 copy this repo into the a new folder called "/tx" inside of simple_openwebrx
 #### Nginx: 
 configure nginx, configure https with certificates add following segment into ssl secion and reload/restart nginx:

 >			auth_basic_user_file /etc/apache2/.htpasswd;
 >
 >		        location / {
 >		                # First attempt to serve request as file, then
 >		                # as directory, then fall back to displaying a 404.
 >		                try_files $uri $uri/ =404;
 >		        }
 >
 >		        location /sdr/ {
 >		                proxy_pass http://127.0.0.1:8073/;
 >		                include /etc/nginx/proxy_params;
 >		                proxy_http_version 1.1;
 >		                proxy_set_header Upgrade $http_upgrade;
 >		                proxy_set_header Connection "upgrade";
 >		                proxy_set_header        Host            $host;
 >		                proxy_set_header        X-Real-IP       $remote_addr;
 >	 	                proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;
 >		                proxy_set_header        X-Forwarded-Proto $scheme;
 >		                #proxy_cache             off;
 >
 >		                proxy_set_header Host $http_host;
 >		                proxy_set_header X-Real-IP $remote_addr;
 >		                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
 >		                proxy_set_header X-Forwarded-Proto $scheme; 
 >
 >		        }
 >
 >		        location /tx/ {
 >		                proxy_pass http://127.0.0.1:8074/;
 >		                include /etc/nginx/proxy_params;
 >		                proxy_http_version 1.1;
 >		                proxy_set_header Upgrade $http_upgrade;
 >		                proxy_set_header Connection "upgrade";
 >		                proxy_set_header        Host            $host;
 >
 >
 >		        }

#### for adding users to the .htpasswd use the apache2-utils.


#### for tx.py 
- rigctld
    - start rigctl -l and find id of transceiver
    - replace id in tx.py at "config_rig['rigctl_cmd']=" and set communication port 

- ffmpeg
  to configure and test the audio output device following parameters can be used:  
  >
  > ffmpeg -f lavfi -i sine=f=440:b=5 -shortest -ac 2 -f alsa hw:1,0
  >

  the parameters after "-f" indicates the output device, alsa seemed to have the shortest latency.    
  To get the correct alsa device "aplay -l" shows available devices  
  finally replace the -f secion in tx.py at "config_audio_out_cmd="  

- custom scripts
  for powering the TX device on and off seperate custom (script)-paths can be set
  > config_cmd['TX_PWR_ON']=  
	> config_cmd['TX_PWR_OFF']=   

  for switching anything additionally from RX to TX externally scripts can be used as well  
  
  > config_cmd['TX']=              
  > config_cmd['RX']=  
  
  if nothing should be done, use some dummy commands like `"echo 'test'"`  


 - start tx.py and the usual openwebrx interface should be available in the subdirectory https://\<HOST\>/sdr

#### debugging rigctld
copy the `config_rig['rigctl_cmd']` and excuting the command by hand,  
change rigctld to rigctl and remove "-t 4532"   
`"rigctld -m 1023 -s 9600 -r /dev/ttyUSB0 -P RTS -t 4532"` => to => `"rigctl -m 1023 -s 9600 -r /dev/ttyUSB0 -P RTS"`  
  
if everything works you can write "f<return>" and the VCO frequency set should be printed  
  
if a client is conneted using the browser and "connected to tx" rigctld can be tested using netcat  
`nc 127.0.0.1 4532`  
again typeing "f<return>" should print the VCO frequency  
if no client is connected in the TX mode, rigctl and depending on custom scripts, also the transceiver is not running.  




  
