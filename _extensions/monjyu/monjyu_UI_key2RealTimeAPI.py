#!/usr/bin/env python
# -*- coding: utf-8 -*-

# ------------------------------------------------
# COPYRIGHT (C) 2014-2024 Mitsuo KONDOU.
# This software is released under the not MIT License.
# Permission from the right holder is required for use.
# https://github.com/ClipnGPT
# Thank you for keeping the rules.
# ------------------------------------------------

import sys
import os
import time
import datetime
import codecs
import glob

import json
import pyaudio
import base64
import websocket

import queue
import threading

from pynput import keyboard
#from pynput.keyboard import Controller


# インターフェース
config_path  = '_config/'
config_file1 = 'RiKi_Monjyu_key.json'
config_file2 = 'RiKi_ClipnGPT_key.json'

# realTimeAPI 設定
MODEL = "gpt-4o-realtime-preview-2024-10-01"

# 音声ストリーム 設定
INPUT_CHUNK = 2400
INPUT_RATE = 24000
FORMAT = pyaudio.paInt16
CHANNELS = 1
OUTPUT_CHUNK = 2400
OUTPUT_RATE = 24000



class _key2Action:

    def __init__(self, runMode='assistant', ):
        self.runMode = runMode

        # APIキーを取得
        if (os.path.isfile(config_path + config_file1)):
            with codecs.open(config_path + config_file1, 'r', 'utf-8') as f:
                self.config_dic = json.load(f)
        if (os.path.isfile(config_path + config_file2)):
            with codecs.open(config_path + config_file2, 'r', 'utf-8') as f:
                self.config_dic = json.load(f)
        elif (os.path.isfile('../../' + config_path + config_file1)):
            with codecs.open('../../' + config_path + config_file1, 'r', 'utf-8') as f:
                self.config_dic = json.load(f)
        elif (os.path.isfile('../../' + config_path + config_file2)):
            with codecs.open('../../' + config_path + config_file2, 'r', 'utf-8') as f:
                self.config_dic = json.load(f)
        openai_key_id = self.config_dic['openai_key_id']

        # realTimeAPI クラス
        self.realTimeAPI = _realtime_api_class(api_key=openai_key_id, model=MODEL, )

        # キーボード監視 開始
        self.start_kb_listener()

    # キーボード監視 開始
    def start_kb_listener(self):
        self.last_ctrl_l_time  = 0
        self.last_ctrl_l_count = 0
        self.last_ctrl_r_time  = 0
        self.last_ctrl_r_count = 0
        self.kb_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.kb_listener.start()

    # キーボード監視 終了
    def stop_kb_listener(self):
        if self.kb_listener:
            self.kb_listener.stop()

    # キーボードイベント
    def on_press(self, key):
        if   (key == keyboard.Key.ctrl_l)  or (key == keyboard.Key.ctrl_r):
            pass
        else:
            self.last_ctrl_l_time  = 0
            self.last_ctrl_l_count = 0
            self.last_ctrl_r_time  = 0
            self.last_ctrl_r_count = 0

    def on_release(self, key):

        # --------------------
        # ctrl_l キー
        # --------------------
        if (key == keyboard.Key.ctrl_l):
            press_time = time.time()
            if ((press_time - self.last_ctrl_l_time) > 1):
                self.last_ctrl_l_time  = press_time
                self.last_ctrl_l_count = 1
            else:
                self.last_ctrl_l_count += 1
                if (self.last_ctrl_l_count < 3):
                    self.last_ctrl_l_time = press_time
                else:
                    self.last_ctrl_l_time  = 0
                    self.last_ctrl_l_count = 0
                    #print("Press ctrl_l x 3 !")

                    # キー操作監視 停止
                    self.stop_kb_listener()

                    # realTimeAPI クラス
                    if self.realTimeAPI.ws is None:
                        self.realTimeAPI.start()
                    else:
                        self.realTimeAPI.stop()

                    #keycontrol = Controller()
                    #keycontrol.press(keyboard.Key.ctrl)
                    #keycontrol.release(keyboard.Key.ctrl)

                    # キー操作監視 再開
                    self.start_kb_listener()

        # --------------------
        # ctrl_r キー
        # --------------------
        elif (key == keyboard.Key.ctrl_r):
            press_time = time.time()
            if ((press_time - self.last_ctrl_r_time) > 1):
                self.last_ctrl_r_time  = press_time
                self.last_ctrl_r_count = 1
            else:
                self.last_ctrl_r_count += 1
                if (self.last_ctrl_r_count < 3):
                    self.last_ctrl_r_time = press_time
                else:
                    self.last_ctrl_r_time  = 0
                    self.last_ctrl_r_count = 0
                    #print("Press ctrl_r x 3 !")

                    # キー操作監視 停止
                    self.stop_kb_listener()
               
                    # realTimeAPI クラス
                    if self.realTimeAPI.ws is None:
                        self.realTimeAPI.start()
                    else:
                        self.realTimeAPI.stop()

                    #keycontrol = Controller()
                    #keycontrol.press(keyboard.Key.ctrl)
                    #keycontrol.release(keyboard.Key.ctrl)

                    # キー操作監視 再開
                    self.start_kb_listener()

        else:
            self.last_ctrl_l_time  = 0
            self.last_ctrl_l_count = 0
            self.last_ctrl_r_time  = 0
            self.last_ctrl_r_count = 0



class _realtime_api_class:
    def __init__(self, api_key, model, ):
        self.WS_URL = f"wss://api.openai.com/v1/realtime?model={ model }"
        self.HEADERS = {
            "Authorization": "Bearer " + api_key,
            "OpenAI-Beta": "realtime=v1"
        }
        self.audio_send_queue = queue.Queue()
        self.audio_receive_queue = queue.Queue()
        self.break_flag = False
        self.ws = None

    def base64_to_pcm16(self, audio_base64):
        audio_data = base64.b64decode(audio_base64)
        return audio_data

    def pcm16_to_base64(self, audio_data):
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        return audio_base64

    def input_audio_to_queue(self, input_stream, CHUNK):
        try:
            while (not self.ws is None) and (not self.break_flag):
                audio_data = input_stream.read(CHUNK, exception_on_overflow=False)
                self.audio_send_queue.put(audio_data)
        except Exception as e:
            print(f"input_audio_to_queue: {e}")
        self.break_flag = True
        return True

    def send_audio_from_queue(self):
        try:
            while (not self.ws is None) and (not self.break_flag):
                audio_data = self.audio_send_queue.get()
                if audio_data is None:
                    continue
                
                audio_base64 = self.pcm16_to_base64(audio_data)
                audio_event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_base64
                }
                self.ws.send(json.dumps(audio_event))
                time.sleep(0.01)
        except Exception as e:
            print(f"send_audio_from_queue: {e}")
        self.break_flag = True
        return True

    def receive_audio_to_queue(self):
        try:
            print("assistant: ", end="", flush=True)
            while (not self.ws is None) and (not self.break_flag):
                response = self.ws.recv()
                if response:
                    response_data = json.loads(response)
                    type = response_data.get('type')
                    if type is not None:
                        print(type)
                        if type == "response.audio_transcript.delta":
                            print(response_data["delta"], end="", flush=True)
                        elif type == "response.audio_transcript.done":
                            print("\nassistant: ", end="", flush=True)
                        elif type == "conversation.item.input_audio_transcription.completed":
                            print("\n↪︎by user messages: ", response_data["transcript"])
                        elif type == "rate_limits.updated":
                            print(f"Rate limits: {response_data['rate_limits'][0]['remaining']} requests remaining.")
                        elif type == "input_audio_buffer.speech_started":
                            while not self.audio_receive_queue.empty():
                                self.audio_receive_queue.get() 
                        elif type == "response.audio.delta":
                            audio_base64_response = response_data["delta"]
                            if audio_base64_response:
                                pcm16_audio = self.base64_to_pcm16(audio_base64_response)
                                self.audio_receive_queue.put(pcm16_audio)
        except Exception as e:
            print(f"receive_audio_to_queue: {e}")
        self.break_flag = True
        return True

    def output_audio_from_queue(self, output_stream):
        try:
            while (not self.ws is None) and (not self.break_flag):
                pcm16_audio = self.audio_receive_queue.get()
                if pcm16_audio:
                    output_stream.write(pcm16_audio)
        except Exception as e:
            print(f"output_audio_from_queue: {e}")
        self.break_flag = True
        return True

    def start(self):
        self.main_thread = threading.Thread(target=self._main, daemon=True)
        self.main_thread.start()
        return True

    def stop(self):
        self.break_flag = True
        self.main_thread.join()
        return True

    def _main(self):
        try:
            # 起動
            self.break_flag = False
            if (self.ws is None):
                self.ws = websocket.create_connection(self.WS_URL, header=self.HEADERS)
                print("WebSocketに接続しました。")

                update_request = {
                    "type": "session.update",
                    "session": {
                        "modalities": ["audio", "text"],
                        "instructions": "あなたは美しい日本語を話す賢いアシスタントです。",
                        "voice": "alloy",
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                        },
                        "input_audio_transcription": {
                            "model": "whisper-1"
                        }
                    }
                }
                self.ws.send(json.dumps(update_request))

                audio_stream = pyaudio.PyAudio()
                input_stream = audio_stream.open(format=FORMAT, channels=CHANNELS, rate=INPUT_RATE, input=True, frames_per_buffer=INPUT_CHUNK)
                output_stream = audio_stream.open(format=FORMAT, channels=CHANNELS, rate=OUTPUT_RATE, output=True, frames_per_buffer=OUTPUT_CHUNK)

                threads = [
                    threading.Thread(target=self.input_audio_to_queue, args=(input_stream, INPUT_CHUNK), daemon=True),
                    threading.Thread(target=self.send_audio_from_queue, daemon=True),
                    threading.Thread(target=self.receive_audio_to_queue, daemon=True),
                    threading.Thread(target=self.output_audio_from_queue, args=(output_stream,), daemon=True)
                ]

                for thread in threads:
                    thread.start()

            # 待機
            while (not self.break_flag):
                time.sleep(1)

        except Exception as e:
            print(f"_main: {e}")
        self.thread_break = True

        # 停止
        self.break_flag = True
        #for thread in threads:
        #    thread.join()
        time.sleep(1.00)

        # 解放
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        audio_stream.terminate()
        if self.ws and self.ws.connected:
            self.ws.close()
            self.ws = None
            print("WebSocketに切断しました。")
        return True



class _class:

    def __init__(self, ):
        self.version   = "v0"
        self.func_name = "extension_UI_key2RealTimeAPI"
        self.func_ver  = "v0.20241008"
        self.func_auth = "h0MmuBSfyHFVSPQ+uqVSZCO6MHFKi8TRGjoM6OG2SpUdF2P/S25GWoK6O8gf4Z6d"
        self.function  = {
            "name": self.func_name,
            "description": "拡張ＵＩ_キー(ctrl)連打で、RealTimeAPIを起動または停止する。",
            "parameters": {
                "type": "object",
                "properties": {
                    "runMode": {
                        "type": "string",
                        "description": "実行モード 例) assistant"
                    },
                },
                "required": ["runMode"]
            }
        }

        # 初期設定
        self.runMode = 'assistant'
        self.func_reset()

        # キーボード監視 開始
        self.sub_proc = _key2Action(runMode=self.runMode, )

    def func_reset(self, ):
        return True

    def func_proc(self, json_kwargs=None, ):
        #print(json_kwargs)

        # 引数
        runMode = None
        if (json_kwargs is not None):
            args_dic = json.loads(json_kwargs)
            runMode = args_dic.get('runMode')

        if (runMode is None) or (runMode == ''):
            runMode      = self.runMode
        else:
            self.runMode = runMode

        # 処理

        # 戻り
        dic = {}
        dic['result'] = "ok"
        json_dump = json.dumps(dic, ensure_ascii=False, )
        #print('  --> ', json_dump)
        return json_dump

if __name__ == '__main__':

    ext = _class()
    print(ext.func_proc('{ "runMode" : "assistant" }'))

    time.sleep(60)



