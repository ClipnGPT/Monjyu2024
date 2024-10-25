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

import requests



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

# 定数の定義
CORE_PORT = '8000'
CONNECTION_TIMEOUT = 15
REQUEST_TIMEOUT = 30



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

        # 認証情報
        self.WS_URL = f"wss://api.openai.com/v1/realtime?model={ model }"
        self.HEADERS = {
            "Authorization": "Bearer " + api_key,
            "OpenAI-Beta": "realtime=v1"
        }

        # botFunc
        self.botFunc = None

        # realtime
        self.audio_send_queue = queue.Queue()
        self.audio_receive_queue = queue.Queue()
        self.break_flag = False
        self.ws = None

        # ポート設定等
        self.local_endpoint = f'http://localhost:{ CORE_PORT }'
        self.user_id = 'admin'

    def base64_to_pcm16(self, audio_base64):
        audio_data = base64.b64decode(audio_base64)
        return audio_data

    def pcm16_to_base64(self, audio_data):
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        return audio_base64

    def send_request(self, request_text='',):
        if (request_text is not None) and (request_text != ''):
            print(f" User(text): { request_text }")

            try:
                # text 送信
                request = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [ {
                            "type": "input_text",
                            "text": request_text, 
                        } ]
                    },
                }
                self.ws.send(json.dumps(request))

                # 送信通知
                request = {
                    "type": "response.create",
                }
                self.ws.send(json.dumps(request))

            except Exception as e:
                print(f"send_request: {e}")
                return False

        return True

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

    def receive_proc(self):
        try:
            while (not self.ws is None) and (not self.break_flag):
                response = self.ws.recv()
                if response:
                    response_data = json.loads(response)
                    type  = response_data.get('type')
                    delta = response_data.get('delta')
                    transcript = response_data.get('transcript')
                    if type is not None:
                        if   type == "response.audio.delta":
                            audio_base64_response = response_data["delta"]
                            if audio_base64_response:
                                pcm16_audio = self.base64_to_pcm16(audio_base64_response)
                                self.audio_receive_queue.put(pcm16_audio)
                        elif type == "input_audio_buffer.speech_started":
                            while not self.audio_receive_queue.empty():
                                self.audio_receive_queue.get() 
                        elif type == "response.audio_transcript.delta":
                            pass # stream!
                        elif type == "response.audio_transcript.done":
                            print(f" Realtime : { transcript }")
                            self.post_output_log(outText=transcript, outData=transcript)

                        elif type == "conversation.item.input_audio_transcription.completed":
                            print(f" Audio in : { transcript }")
                            self.post_input_log(reqText=transcript, inpText='')

                        elif type == "response.function_call_arguments.delta":
                            pass # stream!

                        elif type == "response.function_call_arguments.done":
                            #print(response_data)
                            #function_call: {'type': 'response.function_call_arguments.done', 'event_id': 'event_ALmEfkiWKqDURkButy6ao', 'response_id': 'resp_ALmEfMfNpweiZtvT8xuWY', 'item_id': 'item_ALmEfBwmW2hVho7a5ayy7', 'output_index': 0, 'call_id': 'call_kKkSCI8UdT26zFZS', 'name': 'get_location_weather', 'arguments': '{"location":"東京"}'}

                            f_id = response_data.get('call_id')
                            f_name = response_data.get('name')
                            f_kwargs = response_data.get('arguments')
                            hit = False

                            #print()
                            if self.botFunc is not None:
                                for module_dic in self.botFunc.function_modules:
                                    if (f_name == module_dic['func_name']):
                                        hit = True
                                        print(f" Realtime :   function_call '{ module_dic['script'] }' ({ f_name })")
                                        print(f" Realtime :   → { f_kwargs }")

                                        # function 実行
                                        try:
                                            ext_func_proc  = module_dic['func_proc']
                                            res_json = ext_func_proc( f_kwargs )
                                        except Exception as e:
                                            print(e)
                                            # エラーメッセージ
                                            dic = {}
                                            dic['error'] = e 
                                            res_json = json.dumps(dic, ensure_ascii=False, )

                                        # tool_result
                                        print(f" Realtime :   → { res_json }")
                                        #print()

                                        try:
                                            # result 送信
                                            request = {
                                                "type": "conversation.item.create",
                                                "item": {
                                                    "type": "function_call_output",
                                                    "call_id": f_id,
                                                    "output": res_json,
                                                },
                                            }
                                            self.ws.send(json.dumps(request))

                                            # 送信通知
                                            request = {
                                                "type": "response.create",
                                            }
                                            self.ws.send(json.dumps(request))

                                        except Exception as e:
                                            print(f"function_call: {e}")

                        elif type in [
                            "session.created",
                            "session.updated",
                            "response.created",
                            "conversation.item.created",
                            "rate_limits.updated",
                            "response.output_item.added",
                            "conversation.item.created",
                            "response.content_part.added",
                            "response.audio.done",
                            "response.content_part.done",
                            "response.output_item.done",
                            "response.done",
                            "input_audio_buffer.speech_stopped",
                            "input_audio_buffer.committed",
                        ]:
                            pass

                        else:
                            print(response_data)
                    else:
                        print(response_data)
                else:
                    print(response)

        except Exception as e:
            print(f"receive_proc: {e}")
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

                tools = []
                if self.botFunc is not None:
                    for module_dic in self.botFunc.function_modules:
                        #print(module_dic['func_name'])
                        tool = {'type': 'function'} | module_dic['function']
                        tools.append( tool )

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
                        },
                        "tools": tools,
                        "tool_choice": "auto",
                    }
                }
                self.ws.send(json.dumps(update_request))

                audio_stream = pyaudio.PyAudio()
                input_stream = audio_stream.open(format=FORMAT, channels=CHANNELS, rate=INPUT_RATE, input=True, frames_per_buffer=INPUT_CHUNK)
                output_stream = audio_stream.open(format=FORMAT, channels=CHANNELS, rate=OUTPUT_RATE, output=True, frames_per_buffer=OUTPUT_CHUNK)

                threads = [
                    threading.Thread(target=self.input_audio_to_queue, args=(input_stream, INPUT_CHUNK), daemon=True),
                    threading.Thread(target=self.send_audio_from_queue, daemon=True),
                    threading.Thread(target=self.receive_proc, daemon=True),
                    threading.Thread(target=self.output_audio_from_queue, args=(output_stream,), daemon=True),
                    threading.Thread(target=self.tools_debug, daemon=True)
                ]

                for thread in threads:
                    thread.start()

            # 待機
            while (not self.break_flag):
                time.sleep(1.00)

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
            print("WebSocketを切断しました。")
        return True

    def post_input_log(self, reqText='', inpText=''):
        # AI要求送信
        try:
            response = requests.post(
                self.local_endpoint + '/post_input_log',
                json={'user_id': self.user_id, 
                      'request_text': reqText,
                      'input_text': inpText, },
                timeout=(CONNECTION_TIMEOUT, REQUEST_TIMEOUT)
            )
            if response.status_code != 200:
                print('error', f"Error response ({ CORE_PORT }/post_input_log) : {response.status_code} - {response.text}")
        except Exception as e:
            print('error', f"Error communicating ({ CORE_PORT }/post_input_log) : {e}")
        return True

    def post_output_log(self, outText='', outData=''):
        # AI要求送信
        try:
            response = requests.post(
                self.local_endpoint + '/post_output_log',
                json={'user_id': self.user_id, 
                      'output_text': outText,
                      'output_data': outData, },
                timeout=(CONNECTION_TIMEOUT, REQUEST_TIMEOUT)
            )
            if response.status_code != 200:
                print('error', f"Error response ({ CORE_PORT }/post_output_log) : {response.status_code} - {response.text}")
        except Exception as e:
            print('error', f"Error communicating ({ CORE_PORT }/post_output_log) : {e}")
        return True

    def tools_debug(self):
        time.sleep(5.00)
        self.send_request(request_text='日本の３大都市の天気？', )
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
                    "reqText": {
                        "type": "string",
                        "description": "要求文字列 例) おはようございます"
                    },
                },
                "required": ["runMode"]
            }
        }

        # 設定
        self.runMode = 'assistant'

        # キーボード監視 開始
        self.sub_proc = _key2Action(runMode=self.runMode, )

        # 初期化
        self.func_reset()

    def func_reset(self, botFunc=None, ):
        if botFunc is not None:
            self.sub_proc.realTimeAPI.botFunc = botFunc
        return True

    def func_proc(self, json_kwargs=None, ):
        #print(json_kwargs)

        # 引数
        runMode = None
        reqText = None
        if (json_kwargs is not None):
            args_dic = json.loads(json_kwargs)
            runMode = args_dic.get('runMode')
            reqText = args_dic.get('reqText')

        if (runMode is None) or (runMode == ''):
            runMode = self.runMode
        else:
            self.runMode = runMode

        # 処理
        if (reqText != ''):
            if self.sub_proc.realTimeAPI.ws is None:
                self.sub_proc.realTimeAPI.start()
                time.sleep(5.00)
            self.sub_proc.realTimeAPI.send_request(request_text=reqText, )

        # 戻り
        dic = {}
        dic['result'] = "ok"
        json_dump = json.dumps(dic, ensure_ascii=False, )
        #print('  --> ', json_dump)
        return json_dump

if __name__ == '__main__':

    ext = _class()
    print(ext.func_proc('{ "runMode" : "assistant", "reqText" : "" }'))

    time.sleep(2)

    print(ext.func_proc('{ "runMode" : "assistant", "reqText" : "おはようございます" }'))

    time.sleep(60)

