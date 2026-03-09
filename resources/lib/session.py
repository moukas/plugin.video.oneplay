# -*- coding: utf-8 -*-
import sys
import xbmcaddon
import xbmcgui

import json
import time 

from resources.lib.api import API
from resources.lib.profiles import get_profile_id, get_account_id, reset_profiles

class Session:
    def __init__(self):
        self.valid_to = -1
        self.load_session()

    def create_session(self):
        self.get_token()
        self.save_session()

    def enable_service(self, serviceid):
        for service in self.services:
            if serviceid == service:
                self.services[service]['enabled'] = 1
            else:
                self.services[service]['enabled'] = 0
        self.save_session()

    def get_token(self):
        addon = xbmcaddon.Addon()
        api = API()
        def _notify_login_error(default_msg = 'Problém při přihlášení', payload = None):
            message = default_msg
            if isinstance(payload, dict) and 'err' in payload and payload['err']:
                message = str(payload['err'])
            xbmcgui.Dialog().notification('Oneplay', message, xbmcgui.NOTIFICATION_ERROR, 5000)

        post = {"payload":{"command":{"schema":"LoginWithCredentialsCommand","email":addon.getSetting('username'),"password":addon.getSetting('password')}}}
        data = api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/user.login.step', data = post, sensitive = True)
        step = data.get('step') if isinstance(data, dict) else None
        if 'err' in data or not isinstance(step, dict):
            _notify_login_error(payload = data)
            sys.exit()

        if 'bearerToken' not in step:
            schema = str(step.get('schema', ''))
            if 'AccountChooser' not in schema:
                _notify_login_error(payload = data)
                sys.exit()
            accounts = {}
            accounts_ext = {}
            accounts_data = []
            authToken = step.get('authToken') or step.get('authorizationToken')
            if authToken is None:
                _notify_login_error(payload = data)
                sys.exit()
            for account in step.get('accounts', []):
                account_id = account.get('accountId')
                if account_id is None:
                    continue
                account_name = str(account.get('name', account_id))
                account_provider = str(account.get('extId') or account.get('accountProvider') or account_id)
                account_ext_name = account_name + '|' + account_provider
                if account_name not in accounts:
                    accounts[account_name] = account_id
                accounts_ext[account_ext_name] = account_id
                accounts_data.append(account_ext_name)
            if len(accounts_data) == 0:
                _notify_login_error('Nebyl nalezen žádný účet')
                sys.exit()
            account = get_account_id(accounts_data)
            if account is None:
                xbmcgui.Dialog().notification('Oneplay','Nebyl nalezen žádný účet', xbmcgui.NOTIFICATION_ERROR, 5000)
                sys.exit()
            if '|' in account:
                accounts = accounts_ext
            if account not in accounts:
                _notify_login_error(payload = data)
                sys.exit()
            post = {"payload":{"command":{"schema":"LoginWithAccountCommand","accountId":accounts[account],"authCode":authToken}}}
            data = api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/user.login.step', data = post, sensitive = True)
            step = data.get('step') if isinstance(data, dict) else None
            if 'err' in data or not isinstance(step, dict) or 'bearerToken' not in step:
                _notify_login_error(payload = data)
                sys.exit()            

        self.token = step['bearerToken']

        deviceId = step.get('currentUser', {}).get('currentDevice', {}).get('id')
        if deviceId is not None:
            post = {"payload":{"id":deviceId,"name":addon.getSetting('deviceid')}}
            data = api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/user.device.change', data = post, session = self)
            if 'err' not in data:
                post = {"payload":{"screen":"devices"}}
                data = api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/setting.display', data = post, session = self)
                if 'err' not in data and 'screen' in data and 'userDevices' in data['screen']:
                    for device in data['screen']['userDevices']['devices']:
                        if device.get('id') != deviceId and device.get('name') == addon.getSetting('deviceid'):
                            post = {"payload":{"criteria":{"schema":"UserDeviceIdCriteria","id":device['id']}}}
                            api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/user.device.remove', data = post, session = self)

        self.save_session()
        profileId = get_profile_id()
        if profileId is None:
            xbmcgui.Dialog().notification('Oneplay', 'Nebyl nalezen žádný profil', xbmcgui.NOTIFICATION_ERROR, 5000)
            sys.exit()
        if len(str(addon.getSetting('profile_pin'))) > 0:
            post = {"payload":{"profileId":profileId},"authorization":[{"schema":"PinRequestAuthorization","pin":str(addon.getSetting('profile_pin')),"type":"profile"}]}
        else:
            post = {"payload":{"profileId":profileId}}
        data = api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/user.profile.select', data = post, session = self)
        if 'err' in data or 'bearerToken' not in data:
            if 'err' in data and data['err'] == 'Profil nenalezen':
                reset_profiles()
            profileId = get_profile_id()
            if profileId is None:
                xbmcgui.Dialog().notification('Oneplay', 'Nebyl nalezen žádný profil', xbmcgui.NOTIFICATION_ERROR, 5000)
                sys.exit()
            if len(str(addon.getSetting('profile_pin'))) > 0:
                post = {"payload":{"profileId":profileId},"authorization":[{"schema":"PinRequestAuthorization","pin":str(addon.getSetting('profile_pin')),"type":"profile"}]}
            else:
                post = {"payload":{"profileId":profileId}}
            data = api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/user.profile.select', data = post, session = self)            
            if 'err' in data or 'bearerToken' not in data:
                if 'err' in data:
                    xbmcgui.Dialog().notification('Oneplay', str(data['err']), xbmcgui.NOTIFICATION_ERROR, 5000)
                else:
                    xbmcgui.Dialog().notification('Oneplay', 'Problém při přihlášení', xbmcgui.NOTIFICATION_ERROR, 5000)
                sys.exit()
        self.token = data['bearerToken']

    def reload_profile(self):
        addon = xbmcaddon.Addon()
        api = API()
        profileId = get_profile_id()
        if profileId is None:
            xbmcgui.Dialog().notification('Oneplay', 'Nebyl nalezen žádný profil', xbmcgui.NOTIFICATION_ERROR, 5000)
            sys.exit()
        if len(str(addon.getSetting('profile_pin'))) > 0:
            post = {"payload":{"profileId":profileId},"authorization":[{"schema":"PinRequestAuthorization","pin":str(addon.getSetting('profile_pin')),"type":"profile"}]}
        else:
            post = {"payload":{"profileId":profileId}}
        data = api.call_api(url = 'https://http.cms.jyxo.cz/api/v1.6/user.profile.select', data = post, session = self)
        if 'err' in data or 'bearerToken' not in data:
            if 'err' in data:
                xbmcgui.Dialog().notification('Oneplay', str(data['err']), xbmcgui.NOTIFICATION_ERROR, 5000)
            else:
                xbmcgui.Dialog().notification('Oneplay', 'Problém při přihlášení', xbmcgui.NOTIFICATION_ERROR, 5000)
            sys.exit()
        self.token = data['bearerToken']
        self.save_session()

    def load_session(self):
        from resources.lib.settings import Settings
        settings = Settings()
        data = settings.load_json_data({'filename' : 'session.txt', 'description' : 'session'})
        self.services = None
        if data is not None:
            try:
                data = json.loads(data)
            except ValueError:
                self.create_session()
                return
            if 'valid_to' in data and 'token' in data:
                if int(data['valid_to']) < int(time.time()):
                    self.create_session()
                else:
                    self.token = data['token']
            else:
                self.create_session()
        else:
            self.create_session()

    def save_session(self):
        from resources.lib.settings import Settings
        settings = Settings()
        data = json.dumps({'token' : self.token, 'valid_to' : int(time.time() + 60*60*4)})        
        settings.save_json_data({'filename' : 'session.txt', 'description' : 'session'}, data)

    def remove_session(self):
        from resources.lib.settings import Settings
        settings = Settings()
        settings.reset_json_data({'filename' : 'session.txt', 'description' : 'session'})
        self.valid_to = -1
        self.create_session()
        xbmcgui.Dialog().notification('Oneplay', 'Byla vytvořená nová session', xbmcgui.NOTIFICATION_INFO, 5000)
