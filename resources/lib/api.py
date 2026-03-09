# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon

import json
import gzip 
import socket
import traceback

from websocket import create_connection
import uuid

from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from resources.lib.utils import appVersion

class API:
    def __init__(self):
        self.headers = {'User-Agent' : 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0', 'Accept-Encoding' : 'gzip', 'Accept' : '*/*', 'Content-type' : 'application/json;charset=UTF-8'} 

    def call_api(self, url, data, session = None, sensitive = False):
        addon = xbmcaddon.Addon()
        ws = None
        if session is not None:
            self.headers['Authorization'] = 'Bearer ' + session.token
        elif 'Authorization' in self.headers:
            # Avoid leaking stale Authorization header between calls on reused API instances.
            del self.headers['Authorization']
        if addon.getSetting('log_request_url') == 'true':
            xbmc.log('Oneplay > ' + str(url))
        if addon.getSetting('log_request_url') == 'true' and data != None and sensitive == False:
            xbmc.log('Oneplay > ' + str(data))
        try:
            requestId = str(uuid.uuid4())
            clientId = str(uuid.uuid4())
            ws = create_connection('wss://ws.cms.jyxo.cz/websocket/' + clientId, timeout = 20)
            ws.settimeout(20)
            ws_data = ws.recv()
            ws_data = json.loads(ws_data)
            ws_server_id = ws_data.get('data', {}).get('serverId')
            if ws_server_id is None:
                ws_server_id = ws_data.get('serverId', clientId)
            post = {"deviceInfo":{"deviceType":"web","appVersion":appVersion,"deviceManufacturer":"Unknown","deviceOs":"Linux"},"capabilities":{"async":"websockets"},"context":{"requestId":requestId,"clientId":clientId,"sessionId":ws_server_id,"serverId":ws_server_id}}
            if data is not None:
                post = {**data, **post}
            post = json.dumps(post).encode("utf-8")
            request = Request(url = url , data = post, headers = self.headers)
            response = urlopen(request, timeout = 20)
            if response.getheader("Content-Encoding") == 'gzip':
                gzipFile = gzip.GzipFile(fileobj = response)
                data = gzipFile.read()
            else:
                data = response.read()
            if len(data) > 0:
                data = json.loads(data)
            status = data.get('result', {}).get('status')
            if status == 'Ok':
                ws.close()
                if 'data' in data:
                    return data['data']
                return []
            if status != 'OkAsync':
                xbmc.log('Oneplay > Chyba při volání '+ str(url))
                ws.close()
                return { 'err' : 'Chyba při volání API' }  
            response = None
            for _ in range(8):
                try:
                    ws_message = ws.recv()
                except Exception:
                    break
                if not ws_message:
                    continue
                try:
                    parsed_message = json.loads(ws_message)
                except ValueError:
                    continue
                response_ctx = parsed_message.get('response', {}).get('context', {})
                if response_ctx.get('requestId') == requestId:
                    response = ws_message
                    break
            if addon.getSetting('log_response') == 'true':
                if len(str(response)) > 5000 and addon.getSetting('skip_long') == 'true':
                    xbmc.log('Oneplay > odpověď obdržena (' + str(len(str(response))) + ')')
                else:
                    xbmc.log('Oneplay > ' + str(response))
            if response and len(response) > 0:
                data = json.loads(response)
                response_data = data.get('response', {})
                response_result = response_data.get('result', {})
                response_ctx = response_data.get('context', {})
                if response_result.get('status') != 'Ok' or response_ctx.get('requestId') != requestId:
                    xbmc.log('Oneplay > Chyba při volání '+ str(url))
                    ws.close()
                    if 'message' in response_result:
                        return { 'err' : response_result['message']}
                    else:
                        return { 'err' : 'Chyba při volání API' }  
                ws.close()
                if 'data' in response_data:
                    return response_data['data']
                return []
            else:
                ws.close()
                return { 'err' : 'timeout' }
        except HTTPError as e:
            xbmc.log('Oneplay > Chyba při volání ' + str(url) + ': ' + str(e.reason))
            if ws is not None:
                ws.close()
            return { 'err' : str(e.reason) }  
        except URLError as e:
            xbmc.log('Oneplay > Chyba při volání ' + str(url) + ': ' + str(e.reason))
            if ws is not None:
                ws.close()
            return { 'err' : str(e.reason) }  
        except socket.timeout:
            xbmc.log('Oneplay > Timout volání '+ str(url))
            xbmc.log('Oneplay > Timout volání '+ str(data))
            if ws is not None:
                ws.close()
            return { 'err' : 'timeout' }  
        except socket.error:
            xbmc.log('Oneplay > Timout volání '+ str(url))
            xbmc.log('Oneplay > Timout volání '+ str(data))
            if ws is not None:
                ws.close()
            return { 'err' : 'timeout' }  
        except Exception as e:
            xbmc.log('Oneplay > Neocekavana chyba API ' + str(url) + ': ' + str(e))
            xbmc.log('Oneplay > ' + traceback.format_exc())
            if ws is not None:
                ws.close()
            return { 'err' : 'api_exception' }
