#!/usr/bin/python3
"""

    This file is part of OpenWeb-TX (owt),
    an open-source web transceiver software with a web UI.
    Copyright (c) 2013-2015 by Andras Retzler <randras@sdr.hu>
    Copyright (c) 2022 by LSP/ARCG

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as
    published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.



https://gist.github.com/artizirk/04eb23d957d7916c01ca632bb27d5436
https://websockets.readthedocs.io/en/stable/index.html
https://stackoverflow.com/questions/53689602/python-3-websockets-server-http-server-run-forever-serve-forever


TODO:
    script for putting webrx into dummy mode if 1h without openwebrx
"""
import code
import importlib
import _thread
import time
import datetime
import subprocess
import os
from socketserver import ThreadingMixIn
import fcntl
import random
import threading
import sys
import traceback
from collections import namedtuple

import ctypes
import multiprocessing
import psutil

import signal
import socket
from functools import reduce

#httpnew 202201
import asyncio
import functools
import websockets
from http import HTTPStatus

#pypy compatibility
try: import dl
except: pass
try: import __pypy__
except: pass
pypy="__pypy__" in globals()


config_web_port=8074
config_audio_fifo="test_fifo"
#config_audio_out_cmd=           "opusdec --force-wav - - | aplay -D hw:1,0 -"
#config_audio_out_cmd=           "ffmpeg -y -i - -ac 2 -f alsa hw:1,0"
config_audio_out_cmd=           "ffmpeg -y -re -flags low_delay -thread_queue_size 1024 -i - -ac 2 -f alsa hw:1,0"
#config_audio_out_cmd=           "ffmpeg -y -i - -ac 2 -f pulse '0'"
#config_audio_out_cmd=           "ffmpeg -y -i - -filter_complex \"[0:a][0:a]amerge=inputs=2[a]\" -map \"[a]\" -c 2 -f alsa hw:1,0"
                                #"ffmpeg -y -i - -ac 1 -f wav - | paplay --latency-msec 1"
                                #https://stackoverflow.com/questions/66843134/windows-ffmpeg-send-audio-to-sound-cards-output ffplay?
                                #"mpv -"
                                #"ffmpeg -y -ac 1 -i - -f wav - | paplay --latency-msec 1"
                                #"cat /dev/stdin >>  test2.opus"
                                #ffmpeg -loglevel debug -y -ac 1 -i test2.opus  -f wav - | paplay
                                #"cat "+config_audio_fifo+" | "
                                                    #cmd decoding audio + playback on system
                                                    #signal-chain gets input from stdin
config_rig={}
config_rig['interface']=        "/dev/ttyUSB0"      #serial Port of CAT interface of TRX
config_rig['baud']=             9600                #baud rate of serial port
config_rig['mod_fm']=           "FM 0"              #modulation set for FM-TX
config_rig['mod_lsb']=          "LSB 0"             #modulation set for LSB-TX
config_rig['mod_usb']=          "USB 0"             #modulation set for USB-TX
#config_rig['rigctl_cmd']=       "rigctld -m 1022 -s 9600 -r /dev/ttyUSB0 -P RTS -t 4532" #FT857
config_rig['rigctl_cmd']=       "rigctld -m 1023 -s 9600 -r /dev/ttyUSB0 -P RTS -t 4532" #FT897
#config_rig['rigctl_cmd']=       "rigctld -m 1023 -s 9600 -r /dev/ttyUSB0 -P RTS -t 4532" #FT817
                                #"rigctld -m 120 -s 9600 -r /dev/ttyACM0 --dcd-type=NONE -P RTS" #FT817
                                                    #command to start rigctl software
                                                    #    rigctl -l   lists TRX list für '-m'

config_cmd={}
config_cmd['TX']=              "/home/pi/rf-route.sh tx"         #cmd executed on TX /PTT-ON
config_cmd['RX']=              "/home/pi/rf-route.sh rx"          #cmd executed on RX /PTT-OFF
#config_cmd['TX_PWR_ON']=       "echo 'on'"   #cmd executed on Session start /TX-Power-ON
config_cmd['TX_PWR_ON']=       "/home/pi/rf-route.sh on"   #cmd executed on Session start /TX-Power-ON
#config_cmd['TX_PWR_OFF']=      "echo 'off'"  #cmd executed on Session start /TX-Power-OFF
config_cmd['TX_PWR_OFF']=      "/home/pi/rf-route.sh off"  #cmd executed on Session start /TX-Power-OFF




global openwebrx
openwebrx={} # init for parameter handling
openwebrx['modulation']= "nfm"
global session_sempathor
session_semaphor= 0


def handle_signal_to_del(sig, frame):
    global spectrum_dsp
    if sig == signal.SIGUSR1:
        print("[openwebrx] Verbose status information on USR1 signal")
        print()
        print("time.time() =", time.time())
        print("clients_mutex.locked() =", clients_mutex.locked())
        print("clients_mutex_locker =", clients_mutex_locker)
        if server_fail: print("server_fail = ", server_fail)
        print("spectrum_thread_watchdog_last_tick =", spectrum_thread_watchdog_last_tick)
        print()
        print("clients:",len(clients))
        for client in clients:
            print()
            for key in client._fields:
                print("\t%s = %s"%(key,str(getattr(client,key))))
    elif sig == signal.SIGUSR2:
        code.interact(local=globals())
    else:
        print("[openwebrx] Ctrl+C: aborting.")
        cleanup_clients(True)
        spectrum_dsp.stop()
        os._exit(1) #not too graceful exit

## function start_openwebrx
#
#    function for openwebrx thread, starts openwebrx
#    reads stdin from stdout of openwebrx for frequency and modulation
def start_openwebrx():
    global openwebrx
    p = subprocess.Popen(['python3 -u openwebrx.py 2>&1 '],
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         bufsize=0,
                         shell=True,
                         stdin=None,
                         universal_newlines=True,
                         cwd="../")
    modb=""
    print("startopenwebrx")
    for line in iter(p.stdout.readline, b''):
        #    Sampling at 2400000 S/s.   
        #    Tuned to 144250000 Hz.
        #    [openwebrx-httpd:ws,1] command: SET mod=nfm low_cut=-4000 high_cut=4000 offset_freq=0
        #    csdr_s shift_addition_cc: reinitialized to 0.128407
        #    csdr_s bandpass_fir_fft_cc: filter initialized, low_cut = -0.24875, high_cut = -0.00704792
        
        if "sampling_rate:" in line:
            sampl= line.split("sampling_rate:",1)[1]
            sampl= int(sampl)
            openwebrx['samplerate']=sampl
            print ("S:"+str(sampl))

        elif "center_freq:" in line:
            freq_cent= line.split("center_freq:",1)[1]
            freq_cent= int(freq_cent)
            openwebrx['centerfreq']=freq_cent
            print ("T:"+str(freq_cent))

        elif "SET mod=" in line:
            moda= line.split("SET mod=",1)[1] 
            modb= moda.split(" ")[0]
            print ("M:"+modb)

        elif "csdr_s shift_addition_cc: reinitialized to" in line:
            offset= float(line.split("cc: reinitialized to",1)[1])
            openwebrx['offset']=offset
            print ("s:"+str(offset) )

        if modb == "ssb":
            if "csdr_s bandpass_fir_fft_cc: filter initialized," in line:
                low_cuta= line.split("low_cut = ",1)[1]
                low_cut= low_cuta.split(",",1)[0]
                high_cut= line.split("high_cut = ",1)[1]
                #print("low_cut"+low_cut)
                #print("high_cut"+high_cut)
                low=abs(float(low_cut))
                high=abs(float(high_cut))
                if (low > high):
                    mod="lsb"
                    print("lsb")
                else:
                    mod="usb"
                    print("usb")
                openwebrx['modulation']=mod
        else:
            openwebrx['modulation']=modb

## function asyncWorker
#
#    loop to handle anything for tx operation that might consume time and thereby
#    delay audio samples,
#    quick and dirty communication over global variables "aw_*"
def asyncWorker():
    global process_audio, process_rigctl, rigctl_thread, socket_rigctl
    global aw_trx_on, aw_trx_off, aw_rx, aw_tx, aw_ptt_on, aw_ptt_off  
    #global vars, tcp client, rigctl server
    #start and end rigctl
    #connect tcp client to rigtctl
    #on / off tx
    #rx / tx switch
    #anything else that needs time
    aw_trx_on= 0
    aw_trx_off= 0
    aw_rx= 0
    aw_tx= 0
    aw_ptt_on= 0
    aw_ptt_off= 0  
    while True:
        a=0
        #if tx schould be switched on
        # wait x start rigctl
        if aw_trx_on: 
            aw_trx_on= 0
            print("AW: trx on")
            try:            
                process_txpwr = subprocess.Popen((config_cmd['TX_PWR_ON']), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
            except:
                pass
            #### BEGIN RIGCTL #####
            try:
                process_rigctl = subprocess.Popen([config_rig['rigctl_cmd']], stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
            except:
                pass
            time.sleep(1.2)
            try:
                rigctl_pid= process_rigctl.pid
                rigctl_thread=psutil.Process(rigctl_pid)
                time.sleep(1.8)
                print("rigctl started")
                socket_rigctl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_address = ('127.0.0.1', 4532)
                print('rigctld connecting to {} port {}'.format(*server_address))
                socket_rigctl.connect(server_address)
                socket_rigctl.sendall(b'M LSB 0\n\n')
                print("AW: trx on")
            except:
                pass
        #if tx off, take care of rigctl 
        #end tcp client
        if aw_trx_off:
            aw_trx_off= 0
            try:
                socket_rigctl.sendall(("T 0\n").encode())
                time.sleep(1) 
                socket_rigctl.close()
            except:
                pass
            if rigctl_thread.is_running():
               children=rigctl_thread.children(recursive=True)
               for child in children:
                  try:
                     child.kill()
                  except:
                     pass
            process_txpwr = subprocess.Popen((config_cmd['TX_PWR_OFF']), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
            print("AW: trx off")

        #set tx, relais, 
        if aw_tx:
            aw_tx= 0
            process_tx = subprocess.Popen((config_cmd['TX']), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
            print("AW: relais to TRX")

        
        #set rx, relais
        if aw_rx:
            aw_rx= 0
            process_tx = subprocess.Popen((config_cmd['RX']), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
            print("AW: relais to SDR")

        #set ptt on, relais, rigctl
        if aw_ptt_on:
            aw_ptt_on= 0
            process_tx = subprocess.Popen((config_cmd['TX']), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
            time.sleep(0.27)
            socket_rigctl.sendall(("T 1\n").encode())
            print("AW: ptt on")

        #set ptt of, rigctl, relais
        if aw_ptt_off:
            aw_ptt_off=0
            socket_rigctl.sendall(("T 0\n").encode())
            time.sleep(0.15)
            process_tx = subprocess.Popen((config_cmd['RX']), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
            print("AW: ptt off")
        
    
        #if relais only, to it
        time.sleep(0.01)
    


receiver_failed=spectrum_thread_watchdog_last_tick=rtl_thread=spectrum_dsp=server_fail=None

## function main
#
#    main function, everything gets started here
#         openwebrx
#         asynchron worker
#         webserver
#         websocket
def main():
    global process_audio 
    #global clients, clients_mutex, pypy, lock_try_time, avatar_ctime, cfg, logs
    #global serverfail, rtl_thread, spectrum_thread, ws_kill, sdr_selected, spectrum_kill

    #Change process name to "openwebrx" (to be seen in ps)
    try:
        for libcpath in ["/lib/i386-linux-gnu/libc.so.6","/lib/libc.so.6"]:
            if os.path.exists(libcpath):
                libc = dl.open(libcpath)
                libc.call("prctl", 15, "openwebrx-tx", 0, 0, 0)
                break
    except:
        pass

    #check for external programs #todo, add rigctld, ffmpeg, ...
    if os.system("csdr_s 2> /dev/null") == 32512: #check for csdr
        print("[openwebrx-main] You need to install \"csdr_s\" to run OpenWebRX!\n")
        return
    if os.system("nmux_s --help 2> /dev/null") == 32512: #check for nmux
        print("[openwebrx-main] You need to install an up-to-date version of \"csdr\" that contains the \"nmux\" tool to run OpenWebRX! Please upgrade \"csdr\"!\n")
        return
    #if start_sdr() == False: #moved out for interactive sdr change
    #    return

    #Initialize clients
    clients=[]
  
    #threading.Thread(target = measure_thread_function, args = ()).start()

    #### BEGIN OPENWEBRX ####
    thread_openwebrx = threading.Thread(target = start_openwebrx, args= ()).start()
    #### END OPENWEBRX ####
    
    #### BEGIN AsynWorker ####
    thread_asyncWorker = threading.Thread(target = asyncWorker, args= ()).start()
    #### END AsyncWorker ####


    ####Start HTTP and WS ####
    # set first argument for the handler to current working directory
    handler = functools.partial(process_request, os.getcwd())
    start_server = websockets.serve(ws_process, "0.0.0.0", config_web_port,
                                    process_request=handler)
    print("Running server at http://127.0.0.1 port:"+str(config_web_port))

    asyncio.get_event_loop().run_until_complete(start_server)
    try:
        print("running")
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("server crashed")


def send_302_to_del(self,what):
    self.send_response(302)
    self.send_header('Content-type','text/html')
    self.send_header("Location", "{0}".format(what))
    self.end_headers()
    mime='text/html'
    data="<html><body><h1>Object moved</h1>Please <a href=\"/{0}\">click here</a> to continue.</body></html>".format(what)

    response_headers = [
        ('Server', 'asyncio websocket server'),
        ('Connection', 'close'),
    ]

    response_headers.append(('Content-Type', mime))
    response_headers.append(("Location", "{0}".format(what)))

    # Read the whole file into memory and send it out
    #body = open(full_path, 'rb').read()
    response_headers.append(('Content-Length', str(len(data))))
    return HTTPStatus.FOUND, response_headers, data


    #def do_GET(self):

## function freq_shift
#
#    decides if frequency shift for repeater operation is needed
#    returns new frequency
def freq_shift(f,mod): 
    if (mod == "fm"):
        #10m -100e3
        if (f >= 29620e3 and f<29690e3):
            f=f-100e3
            return f

        #6m -600e3
        if (f >= 51810e3 and f<51990e3):
            f=f-600e3
            return f
    
        #2m  -600e3
        if (f >= 145500e3 and f<146000e3):
            f=f-600e3
            return f

        #70cmi -7.6e6
        if (f >= 438,6375e6 and f<439.6e6):
            f=f-7.6e6
            return f
        #439.8..400 is 9.4 

        #23cm -28e6
        if (f >= 1298.025e6 and f<1298.975e6):
            f=f-28e6
            return f
    else:
        return f

## function write_data
#
#    sends http response for http server
def write_data(path,mime_type,data): #makes http header and content
    #data=data.encode()
    response_headers = [
        ('Server', 'asyncio websocket server'),
        ('Connection', 'close'),
    ]

    response_headers.append(('Content-Type', mime_type))

    response_headers.append(('Content-Length', str(len(data))))
    return HTTPStatus.OK, response_headers, data

## function ws_process
#
#    handles http Websocket requests
#    main task compressed audio => stdout, must not be delayed!
async def ws_process(websocket, path):
    global dsp_plugin, clients_mutex, clients, avatar_ctime, sw_version, receiver_failed, ws_kill, sdr_selected, process_rigctl
    global session_semaphor
    global aw_trx_on, aw_trx_off, aw_rx, aw_tx, aw_ptt_on, aw_ptt_off  

    global process_audio, rigctl_thread, socket_rigctl, openwebrx
    print("New WebSocket connection from", websocket.remote_address)

    path=path.replace("..","")
    path_temp_parts=path.split("?")
    path=path_temp_parts[0]
    client_address= websocket.remote_address[0]
    session_is_mine= 0 #1 if this is the active session
    try:
        if path[:4]=="/ws/": 
            loopstat=0
            print("[openwebrx-ws] Client requested WebSocket connection")
            try:
                #check if rigctl is still running, othervise return
                #TODO send error ws-msg to client
                if session_semaphor == 0 and path[:4]=="/ws/":
                    session_semaphor= 1
                    session_is_mine= 1
                #elif path[:4] != "/wc/":
                #    return
                if session_is_mine :
                    process_audio = subprocess.Popen((config_audio_out_cmd), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
                    
                    print("process_audio started")
                    #switch tx power on
                    aw_trx_on= 1 
                else:
                    print("WS wrong session, semaphor!")
                    raise ValueError('WS wrong session, semphor!') 
                #send default parameters
                #startstr=("MSG center_freq={0} bandwidth={1} fft_size={2} fft_fps={3} audio_compression={4} fft_compression={5} max_clients={6} sdr={7} setup".format(str(cfg.shown_center_freq[sdr_selected]),str(cfg.samp_rate[sdr_selected]),cfg.fft_size,cfg.fft_fps,cfg.audio_compression,cfg.fft_compression,cfg.max_clients,sdr_selected)).encode()    
                     
                while True:

                    try:
                        rdata= await asyncio.wait_for(websocket.recv(), timeout=0.01)
                    except asyncio.TimeoutError:
                        rdata = 0

                    if (rdata != 0):
                        
                        if rdata[:3]=="SET":
                            print(rdata)
                            pairs=rdata[4:].split(" ")
                            for pair in pairs:
                                param_name, param_value = pair.split("=")
                                if param_name == "PTT" and session_is_mine:
                                    if process_rigctl.poll() :
                                        print("no rigctl!")
                                        raise ValueError('No rigctl!')
                                        return
                                                                                        
                                    print("WS start pttW")
                                    freq= float(openwebrx['centerfreq'])-float(openwebrx['samplerate'])*float(openwebrx['offset'])
                                    mod=""
                                    if (openwebrx['modulation'] == "nfm"):
                                        mod= config_rig['mod_fm']
                                    elif (openwebrx['modulation'] == "lsb"):
                                        mod= config_rig['mod_lsb']
                                    elif (openwebrx['modulation'] == "usb"):
                                        mod= config_rig['mod_usb']
                                    if (mod != ""): #if modulation valid
                                        print("F "+str(freq))   
                                        print("center "+str(openwebrx['centerfreq']))   
                                        print("samp "+str(openwebrx['samplerate']))   
                                        print("offset "+str(openwebrx['offset']))   
                                        #TODO 
                                        if (int(param_value)):
                                            freq=freq_shift(freq,mod)
                                            socket_rigctl.sendall(("F "+str(freq)+"\n").encode())
                                            socket_rigctl.sendall(("M "+mod+"\n").encode())
                                            aw_ptt_on= 1
                                        else:
                                            aw_ptt_off=1
                                    else:
                                        error_msg="modulation not valid for TX"
                                        print(error_msg)
                                elif param_name == "low_cut" and -filter_limit <= int(param_value) <= filter_limit:
                                    a=3
                                #TODO
                                #   repater shift, enable/disable
                                #   power
                                else:
                                    print("[openwebrx-httpd:ws] invalid parameter")
                        else:
                            process_audio.stdin.write(rdata)

            except:
                if session_is_mine:
                    process_audio.stdin.close()
                    process_audio.send_signal(signal.SIGINT)
                    aw_trx_off= 1 
                    session_semaphor= 0
                    process_audio = subprocess.Popen(("killall -9 ffmpeg"), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )

                exc_type, exc_value, exc_traceback = sys.exc_info()
                print("[openwebrx-httpd:ws] exception: ",exc_type,exc_value)
                traceback.print_tb(exc_traceback) #TODO digimodes
                if exc_value[0]==32: #"broken pipe", client disconnected
                    print("broken ws, client disconnected")
                elif exc_value[0]==11: #"resource unavailable" on recv, client disconnected
                    print("resource unavailable on recv")
                else:
                    print ("[openwebrx-httpd] error in /ws/ handler: ",exc_type,exc_value)

            try:
                print("do_GET /ws/ delete disconnected")
                if session_is_mine:
                    process_audio.stdin.close()
                    process_audio.send_signal(signal.SIGINT)
                    aw_trx_off= 1 
                    session_semaphor= 0
                    process_audio = subprocess.Popen(("killall -9 ffmpeg"), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )

                exc_type, exc_value, exc_traceback = sys.exc_info()
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                print("[openwebrx-httpd:ws] client cannot be closed: ",exc_type,exc_value)
                traceback.print_tb(exc_traceback)
            finally:
                cmr()
            return
    except:
        print("[openwebrx-httpd:ws] error (@outside)")
        if session_is_mine:
            process_audio.stdin.close()
            process_audio.send_signal(signal.SIGINT)
            aw_trx_off= 1 
            session_semaphor= 0
            process_audio = subprocess.Popen(("killall -9 ffmpeg"), stdout=subprocess.PIPE, stdin=subprocess.PIPE, shell=True )
                                                                                                  
        return


## function process request
#
#    handles http GET requests
async def process_request(sever_root, path, request_headers):
    global dsp_plugin, clients_mutex, clients, avatar_ctime, sw_version, receiver_failed
    if "Upgrade" in request_headers:
        return  # Probably a WebSocket connection
    #return write_data(path,'text/html','bla')
    rootdir = 'htdocs'
    mime_type= 'text/html'
    path=path.replace("..","")
    path_temp_parts=path.split("?")
    path=path_temp_parts[0]
    user_agent= request_headers._list[1][1] # 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:95.0) Gecko/20100101 Firefox/95.0'
    client_address=request_headers._list[0][1] #'127.0.0.1:8073'
    request_param=path_temp_parts[1] if(len(path_temp_parts)>1) else ""
    try:
        if path=="/" or path=="":
            path="/index.html"
        # there's even another cool tip at http://stackoverflow.com/questions/4419650/how-to-implement-timeout-in-basehttpserver-basehttprequesthandler-python

        else:
            f=open(rootdir+path, "rb")
            data=f.read()
            extension=path[(len(path)-4):len(path)]
            extension=extension[2:] if extension[1]=='.' else extension[1:]
            if(("wrx","html","htm","html").count(extension)):
                mime_type= 'text/html'
            elif(extension=="js"):
                mime_type= 'text/javascript'
            elif(extension=="css"):
                mime_type= 'text/css'
            f.close()
            return write_data(path,mime_type,data)

        return
    except IOError:
        #self.send_error(404, 'Invalid path.')
        return HTTPStatus.NOT_FOUND, [], b'404 NOT FOUND'

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        print("[openwebrx-httpd] error (@outside):", exc_type, exc_value)
        traceback.print_tb(exc_traceback)

if __name__=="__main__":
    main()

