import importlib
import json
import re
import sys
import time
import types
import unittest


def install_kodi_stubs(settings=None):
    if settings is None:
        settings = {}

    xbmc = types.ModuleType("xbmc")
    xbmc.log = lambda *args, **kwargs: None
    xbmc.getInfoLabel = lambda *_: "20.0"
    xbmc.Actor = lambda name: name
    xbmc.executebuiltin = lambda *args, **kwargs: None

    xbmcgui = types.ModuleType("xbmcgui")

    class _Dialog:
        def notification(self, *args, **kwargs):
            return None

        def textviewer(self, *args, **kwargs):
            return None

        def select(self, *args, **kwargs):
            return -1

        def yesno(self, *args, **kwargs):
            return False

        def numeric(self, *args, **kwargs):
            return ""

    class _DialogProgressBG:
        def create(self, *args, **kwargs):
            return None

        def update(self, *args, **kwargs):
            return None

        def close(self):
            return None

    xbmcgui.Dialog = _Dialog
    xbmcgui.DialogProgressBG = _DialogProgressBG
    xbmcgui.NOTIFICATION_ERROR = 0
    xbmcgui.NOTIFICATION_INFO = 1

    xbmcaddon = types.ModuleType("xbmcaddon")

    class _Addon:
        def getSetting(self, key):
            return settings.get(key, "")

        def getAddonInfo(self, key):
            if key == "profile":
                return "C:/tmp/"
            return ""

    xbmcaddon.Addon = _Addon

    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = lambda p: p
    xbmcvfs.delete = lambda *args, **kwargs: True
    xbmcvfs.File = None
    xbmcplugin = types.ModuleType("xbmcplugin")
    xbmcplugin.setResolvedUrl = lambda *args, **kwargs: None
    xbmcplugin.addDirectoryItem = lambda *args, **kwargs: None
    xbmcplugin.endOfDirectory = lambda *args, **kwargs: None
    xbmcplugin.setPluginCategory = lambda *args, **kwargs: None
    xbmcplugin.setContent = lambda *args, **kwargs: None

    websocket = types.ModuleType("websocket")
    websocket.create_connection = lambda *_args, **_kwargs: None

    sys.modules["xbmc"] = xbmc
    sys.modules["xbmcgui"] = xbmcgui
    sys.modules["xbmcaddon"] = xbmcaddon
    sys.modules["xbmcvfs"] = xbmcvfs
    sys.modules["xbmcplugin"] = xbmcplugin
    sys.modules["websocket"] = websocket


class TestEpgResilience(unittest.TestCase):
    def setUp(self):
        self._orig_argv = list(sys.argv)
        sys.argv = ["plugin://plugin.video.oneplay", "1", ""]
        install_kodi_stubs(
            {
                "log_request_url": "false",
                "log_response": "false",
                "skip_long": "true",
                "epg_from": "0",
                "epg_to": "1",
                "output_dir": "C:/tmp/",
                "epg_info": "false",
            }
        )

    def tearDown(self):
        sys.argv = self._orig_argv

    def test_parse_iso_ts_with_z_timezone(self):
        epg = importlib.reload(importlib.import_module("resources.lib.epg"))
        ts = epg._parse_iso_ts("2026-01-01T12:34:56.000Z")
        self.assertIsInstance(ts, int)
        self.assertGreater(ts, 0)

    def test_get_epg_data_skips_malformed_items(self):
        epg = importlib.reload(importlib.import_module("resources.lib.epg"))

        class _FakeChannels:
            favorites = 0

            def get_channels_list(self, key):
                if key != "id":
                    raise AssertionError("Unexpected channels list key: %s" % key)
                return {"ch1": {"name": "CT1"}}

        class _FakeApi:
            def call_api(self, url, data, session=None):
                return {
                    "schedule": [
                        {
                            "channelId": "ch1",
                            "items": [
                                {
                                    "startAt": "2026-01-01T10:00:00.000Z",
                                    "endAt": "2026-01-01T11:00:00.000Z",
                                    "title": "Bad - no actions",
                                },
                                {
                                    "startAt": "2026-01-01T11:00:00.000Z",
                                    "endAt": "2026-01-01T12:00:00.000Z",
                                    "title": "Good show",
                                    "description": "Desc",
                                    "referenceId": "r1",
                                    "image": "http://img/{WIDTH}x{HEIGHT}.jpg",
                                    "actions": [
                                        {
                                            "params": {
                                                "contentType": "show",
                                                "payload": {
                                                    "deeplink": {"epgItem": "epg_show_1"}
                                                },
                                            }
                                        }
                                    ],
                                },
                                {
                                    "startAt": "2026-01-01T12:00:00.000Z",
                                    "endAt": "2026-01-01T13:00:00.000Z",
                                    "title": "Good episode",
                                    "description": "Desc2",
                                    "referenceId": "r2",
                                    "image": "http://img/{WIDTH}x{HEIGHT}.jpg",
                                    "actions": [
                                        {
                                            "params": {
                                                "contentType": "episode",
                                                "payload": {"contentId": "content_ep_1"},
                                            }
                                        }
                                    ],
                                },
                            ],
                        }
                    ]
                }

        epg.Session = lambda: object()
        epg.Channels = _FakeChannels
        epg.API = _FakeApi

        data = epg.get_epg_data({"payload": {}}, channel_id=None)
        self.assertEqual(len(data), 2)
        ids = sorted([item["id"] for item in data.values()])
        self.assertEqual(ids, ["content_ep_1", "epg_show_1"])

    def test_get_live_epg_next_is_per_channel(self):
        epg = importlib.reload(importlib.import_module("resources.lib.epg"))
        now = int(time.time())

        epg.get_epg_data = lambda post, channel_id: {
            "a1": {
                "channel_id": "ch1",
                "title": "Now 1",
                "startts": now - 100,
                "endts": now + 100,
            },
            "a2": {
                "channel_id": "ch2",
                "title": "Now 2",
                "startts": now - 50,
                "endts": now + 200,
            },
            "a3": {
                "channel_id": "ch1",
                "title": "Next 1",
                "startts": now + 100,
                "endts": now + 200,
            },
            "a4": {
                "channel_id": "ch2",
                "title": "Next 2",
                "startts": now + 200,
                "endts": now + 400,
            },
        }

        current, upcoming = epg.get_live_epg()
        self.assertEqual(current["ch1"]["title"], "Now 1")
        self.assertEqual(current["ch2"]["title"], "Now 2")
        self.assertEqual(upcoming["ch1"]["title"], "Next 1")
        self.assertEqual(upcoming["ch2"]["title"], "Next 2")

    def test_api_unexpected_exception_returns_error(self):
        api_module = importlib.reload(importlib.import_module("resources.lib.api"))
        api_module.create_connection = lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(RuntimeError("boom"))
        )

        api = api_module.API()
        response = api.call_api("https://example.test", {"payload": {}}, session=None)
        self.assertEqual(response.get("err"), "api_exception")

    def test_api_create_connection_uses_timeout(self):
        api_module = importlib.reload(importlib.import_module("resources.lib.api"))
        captured = {}

        def _fake_create_connection(*args, **kwargs):
            captured["kwargs"] = kwargs
            raise RuntimeError("stop")

        api_module.create_connection = _fake_create_connection
        api = api_module.API()
        api.call_api("https://example.test", {"payload": {}}, session=None)
        self.assertEqual(captured["kwargs"].get("timeout"), 20)

    def test_generate_epg_escapes_icon_src_and_has_xmltv_offset(self):
        written = {}
        iptvsc = importlib.reload(importlib.import_module("resources.lib.iptvsc"))

        class _FakeFile:
            def __init__(self, name, mode):
                self.name = name
                self.mode = mode
                written[self.name] = ""

            def write(self, data):
                if isinstance(data, (bytes, bytearray)):
                    written[self.name] += bytes(data).decode("utf-8")
                else:
                    written[self.name] += str(data)

            def read(self):
                return written.get(self.name, "")

            def close(self):
                return None

        class _FakeChannels:
            def get_channels_list(self, key):
                if key == "channel_number":
                    return {
                        1: {
                            "id": "ch1",
                            "name": "CT 1",
                            "logo": "http://logo/img?a=1&b=2",
                            "liveOnly": False,
                        }
                    }
                if key == "id":
                    return {"ch1": {"name": "CT 1"}}
                return {}

        iptvsc.xbmcvfs.File = _FakeFile
        iptvsc.save_file_test = lambda: 1
        iptvsc.Channels = _FakeChannels
        iptvsc.get_day_epg = lambda _from, _to: {
            1: {
                "channel_id": "ch1",
                "startts": int(time.time()),
                "endts": int(time.time()) + 3600,
                "title": "Title",
                "description": "Desc",
                "poster": "http://poster/p.png?a=1&b=2",
            }
        }

        iptvsc.generate_epg(output_file="out.xml", show_progress=False)

        xml = written["out.xml"]
        self.assertIn("http://logo/img?a=1&amp;b=2", xml)
        self.assertIn("http://poster/p.png?a=1&amp;b=2", xml)
        self.assertRegex(xml, r'start="\d{14} [+-]\d{4}"')

    def test_get_stream_url_returns_tuple_when_mosaic_cancelled(self):
        stream = importlib.reload(importlib.import_module("resources.lib.stream"))

        class _FakeApi:
            def call_api(self, url, data, session=None):
                return {
                    "playerControl": {
                        "liveControl": {
                            "timeline": {"timeShift": {"available": True}},
                            "mosaic": {
                                "items": [
                                    {
                                        "title": "Cam 1",
                                        "play": {
                                            "params": {
                                                "payload": {
                                                    "criteria": {"contentId": "cid.1"}
                                                }
                                            }
                                        },
                                    }
                                ]
                            },
                        }
                    }
                }

        stream.API = _FakeApi
        stream.Session = lambda: object()
        result = stream.get_stream_url({"payload": {"criteria": {}}}, mode="start")
        self.assertEqual(result, (None, None, None, None))

    def test_content_play_detects_channel_dot_as_live(self):
        categories = importlib.reload(importlib.import_module("resources.lib.categories"))
        called = {}
        categories.play_stream = lambda content_id, mode: called.update(
            {"content_id": content_id, "mode": mode}
        )
        categories.content_play(
            json.dumps(
                {
                    "payload": {
                        "criteria": {"contentId": "channel.ct1"},
                    }
                }
            )
        )
        self.assertEqual(called["content_id"], "ct1")
        self.assertEqual(called["mode"], "start")

    def test_channels_group_select_uses_single_batch_update(self):
        channels_module = importlib.reload(importlib.import_module("resources.lib.channels"))
        called = {"count": 0, "map": None}

        class _FakeChannels:
            def get_channels_list(self, bykey=None, visible_filter=True):
                return {
                    "id1": {"name": "A", "visible": True},
                    "id2": {"name": "B", "visible": True},
                }

            def set_visibility_batch(self, visibility_map):
                called["count"] += 1
                called["map"] = visibility_map

        channels_module.Channels = _FakeChannels
        groups = channels_module.Channels_groups.__new__(channels_module.Channels_groups)
        groups.groups = ["grp"]
        groups.channels = {"grp": ["A"]}
        groups.selected = None
        groups.save_channels_groups = lambda: None
        groups.select_group("grp")
        self.assertEqual(called["count"], 1)
        self.assertEqual(called["map"], {"id1": True, "id2": False})

    def test_remove_favourite_missing_item_does_not_crash(self):
        favourites = importlib.reload(importlib.import_module("resources.lib.favourites"))
        favourites.get_favourites = lambda: {"item": {"x": {"title": "X", "image": ""}}}
        favourites.remove_favourite("item", "missing")

    def test_delete_search_removes_all_duplicates(self):
        search = importlib.reload(importlib.import_module("resources.lib.search"))
        search.load_search_history = lambda: ["abc", "x", "abc", "y"]
        captured = {"data": ""}

        class _FakeFile:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def write(self, data):
                captured["data"] += data

        search.open = lambda *args, **kwargs: _FakeFile()
        search.delete_search("abc")
        self.assertEqual(captured["data"], "x\ny\n")

    def test_get_keepalive_url_hls_malformed_does_not_raise(self):
        stream = importlib.reload(importlib.import_module("resources.lib.stream"))

        class _Resp:
            def read(self):
                return b"#EXTM3U"

        keepalive = stream.get_keepalive_url(
            "https://x/index.m3u8?bkm-query=1", _Resp()
        )
        self.assertIsNone(keepalive)

    def test_get_profile_id_handles_missing_active_profile(self):
        profiles = importlib.reload(importlib.import_module("resources.lib.profiles"))
        profiles.get_profiles = lambda active=False, accounts_data=None: None
        self.assertIsNone(profiles.get_profile_id())

    def test_get_account_id_handles_missing_active_account(self):
        profiles = importlib.reload(importlib.import_module("resources.lib.profiles"))
        profiles.get_accounts = lambda active=False, accounts_data=None: None
        self.assertIsNone(profiles.get_account_id())

    def test_router_requires_action_param(self):
        main = importlib.reload(importlib.import_module("main"))
        main.check_settings = lambda: None
        with self.assertRaises(ValueError):
            main.router("foo=bar")

    def test_save_file_test_handles_open_exception(self):
        iptvsc = importlib.reload(importlib.import_module("resources.lib.iptvsc"))
        iptvsc.xbmcvfs.File = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("cannot open")
        )
        self.assertEqual(iptvsc.save_file_test(), 0)

    def test_session_load_session_recovers_from_invalid_json(self):
        session_module = importlib.reload(importlib.import_module("resources.lib.session"))
        settings_module = importlib.reload(importlib.import_module("resources.lib.settings"))

        class _FakeSettings:
            def __init__(self):
                pass

            def load_json_data(self, _file):
                return "{bad-json"

        settings_module.Settings = _FakeSettings
        called = {"created": False}

        def _fake_create_session(self):
            called["created"] = True
            self.token = "newtoken"

        session_module.Session.create_session = _fake_create_session
        session = session_module.Session()
        self.assertTrue(called["created"])
        self.assertEqual(session.token, "newtoken")


if __name__ == "__main__":
    unittest.main()
