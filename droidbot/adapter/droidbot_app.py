import logging
import socket
import subprocess
import time
import json
import struct
import traceback
from .adapter import Adapter

DROIDBOT_APP_REMOTE_ADDR = "tcp:7336"
DROIDBOT_APP_PACKAGE = "io.github.ylimit.droidbotapp"
DROIDBOT_APP_PACKET_HEAD_LEN = 6
ACCESSIBILITY_SERVICE = DROIDBOT_APP_PACKAGE + "/io.github.privacystreams.accessibility.PSAccessibilityService"
MAX_NUM_GET_VIEWS = 5
GET_VIEW_WAIT_TIME = 1


class DroidBotAppConnException(Exception):
    """
    Exception in telnet connection
    """
    pass


class EOF(Exception):
    """
    Exception in telnet connection
    """
    pass


class DroidBotAppConn(Adapter):
    """
    a connection with droidbot app.
    """

    def __init__(self, device=None):
        """
        initiate a droidbot app connection
        :param device: instance of Device
        :return:
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.host = "localhost"
        if device is None:
            from droidbot.device import Device
            device = Device()
        self.device = device
        self.port = self.device.get_random_port()
        self.connected = False
        self.__can_wait = True

        self.sock = None
        self.last_acc_event = None
        self.enable_accessibility_hard = device.enable_accessibility_hard
        self.ignore_ad = device.ignore_ad
        if self.ignore_ad:
            import re
            self.__first_cap_re = re.compile("(.)([A-Z][a-z]+)")
            self.__all_cap_re = re.compile("([a-z0-9])([A-Z])")

    def __id_convert(self, name):
        name = name.replace(".", "_").replace(":", "_").replace("/", "_")
        s1 = self.__first_cap_re.sub(r"\1_\2", name)
        return self.__all_cap_re.sub(r"\1_\2", s1).lower()

    def set_up(self):
        device = self.device
        if DROIDBOT_APP_PACKAGE in device.adb.get_installed_apps():
            self.logger.debug("DroidBot app was already installed.")
        else:
            # install droidbot app
            try:
                from droidbot.resource_utils import get_droidbot_resource
                droidbot_app_path = get_droidbot_resource("droidbotApp.apk")
                install_cmd = ["install", droidbot_app_path]
                self.device.adb.run_cmd(install_cmd)
                self.logger.debug("DroidBot app installed.")
            except Exception:
                self.logger.warning("Failed to install DroidBotApp.")
                traceback.print_exc()

        # device.adb.disable_accessibility_service(ACCESSIBILITY_SERVICE)
        device.adb.enable_accessibility_service(ACCESSIBILITY_SERVICE)

        if ACCESSIBILITY_SERVICE not in device.get_service_names() \
                and self.device.get_sdk_version() < 23 and self.enable_accessibility_hard:
            device.adb.enable_accessibility_service_db(ACCESSIBILITY_SERVICE)
            while ACCESSIBILITY_SERVICE not in device.get_service_names():
                print("Restarting device...")
                time.sleep(1)

        # device.start_app(droidbot_app)
        while ACCESSIBILITY_SERVICE not in device.get_service_names() and self.__can_wait:
            print("Please enable accessibility for DroidBot app manually.")
            time.sleep(1)

    def tear_down(self):
        self.device.uninstall_app(DROIDBOT_APP_PACKAGE)

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # forward host port to remote port
            serial_cmd = "" if self.device is None else "-s " + self.device.serial
            forward_cmd = "adb %s forward tcp:%d %s" % (serial_cmd, self.port, DROIDBOT_APP_REMOTE_ADDR)
            subprocess.check_call(forward_cmd.split())
            self.sock.connect((self.host, self.port))
            import threading
            listen_thread = threading.Thread(target=self.listen_messages)
            listen_thread.start()
        except socket.error:
            self.connected = False
            traceback.print_exc()
            raise DroidBotAppConnException()

    def sock_read(self, rest_len):
        buf = None
        while rest_len:
            pkt = self.sock.recv(rest_len)
            if not pkt:
                raise EOF()
            if not buf:
                buf = pkt
            else:
                buf += pkt
            rest_len -= len(pkt)
        return buf

    def read_head(self):
        header = self.sock_read(DROIDBOT_APP_PACKET_HEAD_LEN)
        data = struct.unpack(">BBI", header)
        return data

    def listen_messages(self):
        self.logger.debug("start listening messages")
        self.connected = True
        try:
            while self.connected:
                _, _, message_len = self.read_head()
                message = self.sock_read(message_len)
                if not isinstance(message, str):
                    message = message.decode()
                self.handle_message(message)
            print("[CONNECTION] %s is disconnected" % self.__class__.__name__)
        except Exception:
            if self.check_connectivity():
                traceback.print_exc()
                # clear self.last_acc_event
                self.logger.warning("Restarting droidbot app")
                self.last_acc_event = None
                self.disconnect()
                self.connect()

    def handle_message(self, message):
        acc_event_idx = message.find("AccEvent >>> ")
        if acc_event_idx >= 0:
            if acc_event_idx > 0:
                self.logger.warning("Invalid data before packet head: " + message[:acc_event_idx])
            body = json.loads(message[acc_event_idx + len("AccEvent >>> "):])
            self.last_acc_event = body
            return

        rotation_idx = message.find("rotation >>> ")
        if rotation_idx >= 0:
            if rotation_idx > 0:
                self.logger.warning("Invalid data before packet head: " + message[:rotation_idx])
            self.device.handle_rotation()
            return

        self.logger.warning("Unhandled message from droidbot app: " + message)
        raise DroidBotAppConnException()

    def check_connectivity(self):
        """
        check if droidbot app is connected
        :return: True for connected
        """
        return self.connected

    def disconnect(self):
        """
        disconnect telnet
        """
        self.connected = False
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception as e:
                print(e)
        try:
            forward_remove_cmd = "adb -s %s forward --remove tcp:%d" % (self.device.serial, self.port)
            p = subprocess.Popen(forward_remove_cmd.split(), stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            out, err = p.communicate()
        except Exception as e:
            print(e)
        self.__can_wait = False

    def __view_tree_to_list(self, view_tree, view_list):
        tree_id = len(view_list)
        view_tree['temp_id'] = tree_id

        bounds = [[-1, -1], [-1, -1]]
        bounds[0][0] = view_tree['bounds'][0]
        bounds[0][1] = view_tree['bounds'][1]
        bounds[1][0] = view_tree['bounds'][2]
        bounds[1][1] = view_tree['bounds'][3]
        width = bounds[1][0] - bounds[0][0]
        height = bounds[1][1] - bounds[0][1]
        view_tree['size'] = "%d*%d" % (width, height)
        view_tree['bounds'] = bounds

        view_list.append(view_tree)
        children_ids = []
        for child_tree in view_tree['children']:
            if self.ignore_ad and child_tree['resource_id'] is not None:
                id_word_list = self.__id_convert(child_tree['resource_id']).split('_')
                if "ad" in id_word_list or \
                   "banner" in id_word_list:
                    continue
            child_tree['parent'] = tree_id
            self.__view_tree_to_list(child_tree, view_list)
            children_ids.append(child_tree['temp_id'])
        view_tree['children'] = children_ids

    def get_views(self, foreground_activity=None):
        get_views_times = 0
        while not self.last_acc_event:
            self.logger.warning("last_acc_event is None, waiting")
            get_views_times += 1
            if get_views_times > MAX_NUM_GET_VIEWS:
                self.logger.warning("cannot get non-None last_acc_event")
                return None
            time.sleep(GET_VIEW_WAIT_TIME)

        if 'view_list' in self.last_acc_event:
            view_list = self.last_acc_event['view_list']
        else:
            import copy
            view_tree = copy.deepcopy(self.last_acc_event['root_node'])
            # print view_tree
            if not view_tree:
                return None
            view_tree['parent'] = -1
            view_list = []
            self.__view_tree_to_list(view_tree, view_list)
            self.last_acc_event['view_list'] = view_list

        # Generate view strings
        if not foreground_activity:
            foreground_activity = self.device.get_top_activity_name()
        if foreground_activity:
            self.__generate_view_strs(view_list, foreground_activity)
        
        return view_list

    def __generate_view_strs(self, view_list, foreground_activity):
        """
        Generate view_str for each view in the view_list
        """
        for view_dict in view_list:
            self.__get_view_str(view_dict, view_list, foreground_activity)

    def __get_view_str(self, view_dict, view_list, foreground_activity):
        """
        Get a string which can represent the given view
        """
        if 'view_str' in view_dict:
            return view_dict['view_str']
        
        view_signature = self.__get_view_signature(view_dict)
        parent_strs = []
        for parent_id in self.__get_all_ancestors(view_dict, view_list):
            parent_strs.append(self.__get_view_signature(view_list[parent_id]))
        parent_strs.reverse()
        
        child_strs = []
        for child_id in self.__get_all_children(view_dict, view_list):
            child_strs.append(self.__get_view_signature(view_list[child_id]))
        child_strs.sort()
        
        view_str = "Activity:%s\nSelf:%s\nParents:%s\nChildren:%s" % \
                   (foreground_activity, view_signature, "//".join(parent_strs), "||".join(child_strs))
        import hashlib
        view_str = hashlib.md5(view_str.encode('utf-8')).hexdigest()
        view_dict['view_str'] = view_str
        return view_str

    @staticmethod
    def __get_view_signature(view_dict):
        """
        Get the signature of the given view
        """
        if 'signature' in view_dict:
            return view_dict['signature']

        view_text = DroidBotAppConn.__safe_dict_get(view_dict, 'text', "None")
        if view_text is None or len(view_text) > 50:
            view_text = "None"

        signature = "[class]%s[resource_id]%s[text]%s[%s,%s,%s]" % \
                    (DroidBotAppConn.__safe_dict_get(view_dict, 'class', "None"),
                     DroidBotAppConn.__safe_dict_get(view_dict, 'resource_id', "None"),
                     view_text,
                     DroidBotAppConn.__key_if_true(view_dict, 'enabled'),
                     DroidBotAppConn.__key_if_true(view_dict, 'checked'),
                     DroidBotAppConn.__key_if_true(view_dict, 'selected'))
        view_dict['signature'] = signature
        return signature

    def __get_all_ancestors(self, view_dict, view_list):
        """
        Get temp view ids of the given view's ancestors
        """
        result = []
        parent_id = self.__safe_dict_get(view_dict, 'parent', -1)
        if 0 <= parent_id < len(view_list):
            result.append(parent_id)
            result += self.__get_all_ancestors(view_list[parent_id], view_list)
        return result

    def __get_all_children(self, view_dict, view_list):
        """
        Get temp view ids of the given view's children
        """
        children = self.__safe_dict_get(view_dict, 'children')
        if not children:
            return set()
        children = set(children)
        for child in children:
            children_of_child = self.__get_all_children(view_list[child], view_list)
            children.union(children_of_child)
        return children

    @staticmethod
    def __key_if_true(view_dict, key):
        return key if (key in view_dict and view_dict[key]) else ""

    @staticmethod
    def __safe_dict_get(view_dict, key, default=None):
        value = view_dict[key] if key in view_dict else None
        return value if value is not None else default


if __name__ == "__main__":
    droidbot_app_conn = DroidBotAppConn()
    droidbot_app_conn.set_up()
    droidbot_app_conn.connect()
