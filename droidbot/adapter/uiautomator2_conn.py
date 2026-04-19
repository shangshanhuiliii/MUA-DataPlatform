import logging
import traceback

import uiautomator2 as u2
from uiautomator2 import AdbBroadcastError

from .adapter import Adapter
from droidbot.constant import ViewsMode

import numpy as np
from . import cv
from .yolo_model_manager import YOLOModelManager

class UIAutomator2ConnException(Exception):
    """
    Exception in UIAutomator2 connection
    """
    pass


class UIAutomator2AppConn(Adapter):
    """
    A connection adapter using UIAutomator2 library for Android automation.
    """

    def __init__(self, device=None):
        """
        Initiate a UIAutomator2 app connection
        :param device: instance of Device
        :return:
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        if device is None:
            from droidbot.device import Device
            device = Device()
        self.device = device
        self.connected = False
        self.u2_device = None
        self.last_view_hierarchy = None
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
        """
        Set up the UIAutomator2 connection
        """
        import time
        try:
            t_start = time.time()
            self.logger.info(f"Setting up UIAutomator2 connection for {self.device.serial}...")

            # Connect to device using UIAutomator2 with timeout
            self.logger.debug("Calling u2.connect()...")
            self.u2_device = u2.connect(self.device.serial)

            t_connect = time.time()
            self.logger.info(f"⏱️ u2.connect() took {t_connect - t_start:.2f}s")
            self.logger.debug("UIAutomator2 device connected")
        except Exception as e:
            self.logger.error(f"Failed to set up UIAutomator2 connection: {e}")
            traceback.print_exc()
            raise UIAutomator2ConnException(f"Setup failed: {e}")

    def tear_down(self):
        """
        Clean up UIAutomator2 connection
        """
        self.disconnect()

    def connect(self):
        """
        Establish connection with UIAutomator2
        """
        try:
            if self.u2_device is None:
                self.u2_device = u2.connect(self.device.serial)
            
            # Test connection
            info = self.u2_device.info
            self.connected = True
            self.logger.debug(f"UIAutomator2 connected to device: {info.get('productName', 'Unknown')}")

            # set fast_input_ime
            self.u2_device.set_fastinput_ime()
        except Exception as e:
            self.connected = False
            self.logger.error(f"Failed to connect with UIAutomator2: {e}")
            traceback.print_exc()
            raise UIAutomator2ConnException(f"Connection failed: {e}")

    def disconnect(self):
        """
        Disconnect UIAutomator2 connection
        """
        self.connected = False
        self.u2_device = None
        self.last_view_hierarchy = None

    def check_connectivity(self):
        """
        Check if UIAutomator2 is connected
        :return: True for connected
        """
        if not self.connected or self.u2_device is None:
            return False
        
        try:
            # Test connectivity by getting device info
            _ = self.u2_device.info
            return True
        except Exception:
            self.connected = False
            return False

    def get_views(self, foreground_activity=None):
        """
        Get view hierarchy using UIAutomator2
        :return: List of views in DroidBot format
        """
        try:
            if not self.check_connectivity():
                self.logger.warning("UIAutomator2 not connected")
                return None

            # Get XML dump from UIAutomator2
            xml_hierarchy = self.u2_device.dump_hierarchy()
            if not xml_hierarchy:
                return None

            # Parse XML and convert to DroidBot view format
            view_list = self.__parse_xml_to_views(xml_hierarchy)
            self.last_view_hierarchy = view_list
            
            # Generate view strings
            if not foreground_activity:
                foreground_activity = self.device.get_top_activity_name()
            if foreground_activity:
                self.__generate_view_strs(view_list, foreground_activity)
            
            return view_list

        except Exception as e:
            self.logger.error(f"Failed to get views via UIAutomator2: {e}")
            traceback.print_exc()
            return None

    def get_views_cv_mode(self, foreground_activity=None):
        """
        Get UI views using cv module (computer vision approach)
        opencv-python need to be installed for this function
        :return: a list of views
        """
        if not self.check_connectivity():
            self.logger.warning("UIAutomator2 not connected")
            return None

        try:
            # Get screenshot as PIL Image
            screenshot = self.u2_device.screenshot()
            if not screenshot:
                self.logger.warning("Failed to get screenshot")
                return None

            # Get dimensions directly from screenshot
            width, height = screenshot.size

            # Convert PIL Image to OpenCV format and find views
            from . import cv
            import cv2
            import numpy as np
            
            # Convert PIL Image to numpy array (OpenCV format)
            img = np.array(screenshot)
            # Convert RGB to BGR for OpenCV
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            
            view_bounds = cv.find_views(img)
            
            # Create root view
            root_view = {
                "class": "CVViewRoot",
                "bounds": [[0, 0], [width, height]],
                "enabled": True,
                "temp_id": 0,
                "visible": True,
                "clickable": False,
                "children": []
            }
            views = [root_view]
            temp_id = 1
            
            # Create child views from detected bounds
            for x, y, w, h in view_bounds:
                view = {
                    "class": "CVView",
                    "bounds": [[x, y], [x + w, y + h]],
                    "enabled": True,
                    "temp_id": temp_id,
                    "signature": cv.calculate_dhash(img[y:y+h, x:x+w]),
                    "parent": 0,
                    "children": [],
                    "visible": True,
                    "clickable": True,
                    "size": f"{w}*{h}"
                }
                views.append(view)
                temp_id += 1
            
            # Update root view children list
            root_view["children"] = list(range(1, temp_id))
            
            # Generate view strings
            if not foreground_activity:
                foreground_activity = self.device.get_top_activity_name()
            if foreground_activity:
                self.__generate_view_strs(views, foreground_activity)
            
            return views

        except Exception as e:
            self.logger.error(f"Failed to get views via CV mode: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    # 适配最新的YOLOmanager
    def get_views_yolo_mode(self, foreground_activity=None):
        if not self.check_connectivity():
            self.logger.warning("UIAutomator2 not connected")
            return None
    
        try:
            screenshot = self.u2_device.screenshot()
            if not screenshot:
                self.logger.warning("Failed to get screenshot")
                return None

            img = np.array(screenshot)
            H, W = img.shape[:2]
            manager = YOLOModelManager() 
            
            results = manager.predict(img)
            if results is None:
                self.logger.warning("YOLO prediction failed, falling back to XML mode")
                return None

            views = [{
                "class": "YOLOViewRoot",
                "bounds": [[0, 0], [W, H]],
                "clickable": False,
                "enabled": True,
                "visible": True,
                "temp_id": 0,
                "children": []
            }]
            temp_id = 1

            if not results or not getattr(results[0], "boxes", None) or len(results[0].boxes) == 0:
                return views

            for box in results[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
        
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(W, x2)
                y2 = min(H, y2)

                if x2 <= x1 or y2 <= y1:
                    continue

                roi = img[y1:y2, x1:x2]
                signature = cv.calculate_dhash(roi)

                views.append({
                    "class": "YOLOView",
                    "bounds": [[x1, y1], [x2, y2]],
                    "enabled": True,
                    "temp_id": temp_id,
                    "signature": signature,
                    "parent": 0,
                    "children": [],
                    "visible": True,
                    "clickable": True,
                    "size": f"{x2 - x1}*{y2 - y1}"
                })
                temp_id += 1

            views[0]["children"] = list(range(1, temp_id))

            if not foreground_activity:
                foreground_activity = self.device.get_top_activity_name()
            if foreground_activity:
                self.__generate_view_strs(views, foreground_activity)

            return views

        except Exception as e:
            self.logger.error(f"YOLO get_views failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def __parse_xml_to_views(self, xml_hierarchy):
        """
        Parse UIAutomator2 XML hierarchy to DroidBot view format
        """
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_hierarchy)
            view_list = []
            
            # Skip the root hierarchy element
            if root.tag == 'hierarchy' and len(list(root)) > 0:
                # Process children
                for child in root:
                    child_id = self.__xml_node_to_view_list(child, view_list, parent_id=-1)
            else:
                self.__xml_node_to_view_list(root, view_list, parent_id=-1)
            
            return view_list
        except Exception as e:
            self.logger.error(f"Failed to parse XML hierarchy: {e}")
            return []

    def __xml_node_to_view_list(self, node, view_list, parent_id=-1):
        """
        Convert XML node to DroidBot view format and add to view list
        """
        view_id = len(view_list)
        
        # Extract bounds
        bounds_str = node.get('bounds', '[0,0][0,0]')
        bounds_parts = bounds_str.replace('[', '').replace(']', ',').split(',')[:-1]
        bounds = [
            [int(bounds_parts[0]), int(bounds_parts[1])],
            [int(bounds_parts[2]), int(bounds_parts[3])]
        ]
        
        # Calculate size
        width = bounds[1][0] - bounds[0][0]
        height = bounds[1][1] - bounds[0][1]
        
        view = {
            'package': node.get('package', ''),
            'visible': node.get('displayed', 'true') == 'true',
            'checkable': node.get('checkable', 'false') == 'true',
            'child_count': len(list(node)),
            'editable': node.get('editable', 'false') == 'true',
            'clickable': node.get('clickable', 'false') == 'true',
            'is_password': node.get('password', 'false') == 'true',
            'focusable': node.get('focusable', 'false') == 'true',
            'enabled': node.get('enabled', 'true') == 'true',
            'content_description': node.get('content-desc', '') or None,
            'children': [],
            'focused': node.get('focused', 'false') == 'true',
            'bounds': bounds,
            'resource_id': node.get('resource-id', '') or None,
            'checked': node.get('checked', 'false') == 'true',
            'text': node.get('text', '') or None,
            'class': node.get('class', ''),
            'scrollable': node.get('scrollable', 'false') == 'true',
            'selected': node.get('selected', 'false') == 'true',
            'long_clickable': node.get('long-clickable', 'false') == 'true',
            'parent': parent_id,
            'temp_id': view_id,
            'size': f"{width}*{height}"
        }

        # Filter ads if enabled
        if self.ignore_ad and view['resource_id']:
            id_word_list = self.__id_convert(view['resource_id']).split('_')
            if "ad" in id_word_list or "banner" in id_word_list:
                return

        view_list.append(view)
        
        # Process children
        children_ids = []
        for child in node:
            child_id = self.__xml_node_to_view_list(child, view_list, view_id)
            if child_id is not None:
                children_ids.append(child_id)
        
        view['children'] = children_ids
        return view_id

    def get_screenshot(self, filename=None):
        """
        Take screenshot using UIAutomator2
        :param filename: path to save the screenshot, if None returns PIL Image
        :return: filename or PIL Image
        """
        if not self.check_connectivity():
            raise UIAutomator2ConnException("Not connected")
        
        try:
            if filename:
                self.u2_device.screenshot(filename)
                return filename
            else:
                return self.u2_device.screenshot()
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {e}")
            return None

    def input_text(self, text, mode=0):
        """
        Input text using UIAutomator2
        :param text: text to input
        :param mode: 0 for set_text (clear and input), 1 for append_text
        :return: True if successful, False otherwise
        """
        if not self.check_connectivity():
            raise UIAutomator2ConnException("Not connected")
        
        try:
            self.u2_device.set_fastinput_ime(True)
            self.u2_device.send_keys(text, clear=(mode == 0))
            return True
        except AdbBroadcastError:
            try:
                self.u2_device.set_fastinput_ime(True)
                self.u2_device.send_keys(text)
                return True
            except Exception as e:
                self.logger.warning(f"Second text input attempt failed, fallback to clipboard: {e}")
                try:
                    if mode == 0:
                        self.u2_device.jsonrpc.clearInputText()
                    self.u2_device.set_clipboard(text)
                    if self.u2_device.clipboard != text:
                        raise UIAutomator2ConnException("setClipboard failed")
                    self.u2_device.jsonrpc.pasteClipboard()
                    return True
                except Exception as clipboard_e:
                    self.logger.error(f"Failed to input text '{text}' with clipboard fallback: {clipboard_e}")
                    return False
        except Exception as e:
            self.logger.error(f"Failed to input text '{text}': {e}")
            return False

    def touch(self, x, y):
        """
        Touch at specified coordinates using UIAutomator2
        :param x: x coordinate
        :param y: y coordinate
        :return: True if successful
        """
        if not self.check_connectivity():
            raise UIAutomator2ConnException("Not connected")
        
        try:
            self.u2_device.click(x, y)
            return True
        except Exception as e:
            self.logger.error(f"Failed to touch at ({x}, {y}): {e}")
            return False

    def long_touch(self, x, y, duration=2000):
        """
        Long touch at specified coordinates using UIAutomator2
        :param x: x coordinate
        :param y: y coordinate  
        :param duration: duration in milliseconds
        :return: True if successful
        """
        if not self.check_connectivity():
            raise UIAutomator2ConnException("Not connected")
        
        try:
            # Convert duration from ms to seconds
            duration_sec = duration / 1000.0
            self.u2_device.long_click(x, y, duration_sec)
            return True
        except Exception as e:
            self.logger.error(f"Failed to long touch at ({x}, {y}): {e}")
            return False

    def drag(self, start_xy, end_xy, duration=1000):
        """
        Drag from start point to end point using UIAutomator2
        :param start_xy: starting point (x, y)
        :param end_xy: ending point (x, y)
        :param duration: duration in milliseconds
        :return: True if successful
        """
        if not self.check_connectivity():
            raise UIAutomator2ConnException("Not connected")
        
        try:
            (x0, y0) = start_xy
            (x1, y1) = end_xy
            # Convert duration from ms to seconds
            duration_sec = duration / 1000.0
            self.u2_device.swipe(x0, y0, x1, y1, duration_sec)
            return True
        except Exception as e:
            self.logger.error(f"Failed to drag from {start_xy} to {end_xy}: {e}")
            return False

    def press_key(self, key_code):
        """
        Press a key using UIAutomator2
        :param key_code: key code to press (ADB format or UIAutomator2 format)
        :return: True if successful
        """
        if not self.check_connectivity():
            raise UIAutomator2ConnException("Not connected")
        
        try:
            # Convert ADB key code to UIAutomator2 key name if needed
            u2_key = self.__convert_key_code(key_code)
            self.u2_device.press(u2_key)
            return True
        except Exception as e:
            self.logger.error(f"Failed to press key '{key_code}': {e}")
            return False

    def __convert_key_code(self, key_code):
        """
        Convert ADB key code to UIAutomator2 key name
        :param key_code: ADB key code (int, str number, or KEYCODE_* format)
        :return: UIAutomator2 key name
        """
        # Handle KEYCODE_* format from ADB
        if isinstance(key_code, str) and key_code.startswith("KEYCODE_"):
            # Convert KEYCODE_HOME to home
            return key_code.replace("KEYCODE_", "").lower()
        
        # UIAutomator2 supports numbers directly, so return as is
        return key_code

    def unlock(self):
        """
        Unlock the screen of the device using UIAutomator2
        :return: True if successful
        """
        if not self.check_connectivity():
            raise UIAutomator2ConnException("Not connected")
        
        try:
            # Use UIAutomator2's built-in unlock method
            self.u2_device.unlock()
            return True
        except Exception as e:
            self.logger.error(f"Failed to unlock using UIAutomator2: {e}")
            # Fallback to manual key sequence like ADB does
            try:
                self.u2_device.press("menu")
                self.u2_device.press("back")
                return True
            except Exception as e2:
                self.logger.error(f"Failed to unlock with fallback method: {e2}")
                return False

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

        view_text = UIAutomator2AppConn.__safe_dict_get(view_dict, 'text', "None")
        if view_text is None or len(view_text) > 50:
            view_text = "None"

        signature = "[class]%s[resource_id]%s[text]%s[%s,%s,%s]" % \
                    (UIAutomator2AppConn.__safe_dict_get(view_dict, 'class', "None"),
                     UIAutomator2AppConn.__safe_dict_get(view_dict, 'resource_id', "None"),
                     view_text,
                     UIAutomator2AppConn.__key_if_true(view_dict, 'enabled'),
                     UIAutomator2AppConn.__key_if_true(view_dict, 'checked'),
                     UIAutomator2AppConn.__key_if_true(view_dict, 'selected'))
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
    uiautomator2_conn = UIAutomator2AppConn()
    uiautomator2_conn.set_up()
    uiautomator2_conn.connect()
