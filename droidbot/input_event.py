import json
import os
import random
import time
from abc import abstractmethod

from . import utils
from .intent import Intent

POSSIBLE_KEYS = [
    "BACK",
    "MENU",
    "HOME"
]

# Unused currently, but should be useful.
POSSIBLE_BROADCASTS = [
    "android.intent.action.AIRPLANE_MODE_CHANGED",
    "android.intent.action.BATTERY_CHANGED",
    "android.intent.action.BATTERY_LOW",
    "android.intent.action.BATTERY_OKAY",
    "android.intent.action.BOOT_COMPLETED",
    "android.intent.action.DATE_CHANGED",
    "android.intent.action.DEVICE_STORAGE_LOW",
    "android.intent.action.DEVICE_STORAGE_OK",
    "android.intent.action.INPUT_METHOD_CHANGED",
    "android.intent.action.INSTALL_PACKAGE",
    "android.intent.action.LOCALE_CHANGED",
    "android.intent.action.MEDIA_EJECT",
    "android.intent.action.MEDIA_MOUNTED",
    "android.intent.action.MEDIA_REMOVED",
    "android.intent.action.MEDIA_SHARED",
    "android.intent.action.MEDIA_UNMOUNTED",
    "android.intent.action.NEW_OUTGOING_CALL",
    "android.intent.action.OPEN_DOCUMENT",
    "android.intent.action.OPEN_DOCUMENT_TREE",
    "android.intent.action.PACKAGE_ADDED",
    "android.intent.action.PACKAGE_CHANGED",
    "android.intent.action.PACKAGE_DATA_CLEARED",
    "android.intent.action.PACKAGE_FIRST_LAUNCH",
    "android.intent.action.PACKAGE_FULLY_REMOVED",
    "android.intent.action.PACKAGE_INSTALL",
    "android.intent.action.PACKAGE_REMOVED",
    "android.intent.action.PACKAGE_REPLACED",
    "android.intent.action.PACKAGE_RESTARTED",
    "android.intent.action.PACKAGE_VERIFIED",
    "android.intent.action.PASTE",
    "android.intent.action.POWER_CONNECTED",
    "android.intent.action.POWER_DISCONNECTED",
    "android.intent.action.POWER_USAGE_SUMMARY",
    "android.intent.action.PROVIDER_CHANGED",
    "android.intent.action.QUICK_CLOCK",
    "android.intent.action.REBOOT",
    "android.intent.action.SCREEN_OFF",
    "android.intent.action.SCREEN_ON",
    "android.intent.action.SET_WALLPAPER",
    "android.intent.action.SHUTDOWN",
    "android.intent.action.TIMEZONE_CHANGED",
    "android.intent.action.TIME_CHANGED",
    "android.intent.action.TIME_TICK",
    "android.intent.action.UID_REMOVED",
    "android.intent.action.UNINSTALL_PACKAGE",
    "android.intent.action.USER_BACKGROUND",
    "android.intent.action.USER_FOREGROUND",
    "android.intent.action.USER_INITIALIZE",
    "android.intent.action.USER_PRESENT",
    "android.intent.action.VOICE_COMMAND",
    "android.intent.action.WALLPAPER_CHANGED",
    "android.intent.action.WEB_SEARCH"
]

KEY_KeyEvent = "key"
KEY_ManualEvent = "manual"
KEY_ExitEvent = "exit"
KEY_TouchEvent = "touch"
KEY_LongTouchEvent = "long_touch"
KEY_SelectEvent = "select"
KEY_UnselectEvent = "unselect"
KEY_SwipeEvent = "swipe"
KEY_ScrollEvent = "scroll"
KEY_SetTextEvent = "set_text"
KEY_PutTextEvent = "put_text"
KEY_IntentEvent = "intent"
KEY_SpawnEvent = "spawn"
KEY_KillAppEvent = "kill_app"


class InvalidEventException(Exception):
    pass


class InputEvent(object):
    """
    The base class of all events
    """
    def __init__(self):
        self.event_type = None
        self.log_lines = None

    def to_dict(self):
        return self.__dict__

    def to_dict_relative(self, device_width=None, device_height=None):
        """
        Convert event to dictionary with relative coordinates (0-1000)
        :param device_width: device screen width
        :param device_height: device screen height
        :return: dictionary with relative coordinates
        """
        result = self.__dict__.copy()
        
        # Convert point coordinates if they exist
        if hasattr(self, 'x') and hasattr(self, 'y'):
            if self.x is not None and device_width:
                result['x'] = self.convert_coord_to_relative(self.x, device_width)
            if self.y is not None and device_height:
                result['y'] = self.convert_coord_to_relative(self.y, device_height)
                
        # Convert start/end coordinates for SwipeEvent
        if hasattr(self, 'start_x') and hasattr(self, 'start_y'):
            if self.start_x is not None and device_width:
                result['start_x'] = self.convert_coord_to_relative(self.start_x, device_width)
            if self.start_y is not None and device_height:
                result['start_y'] = self.convert_coord_to_relative(self.start_y, device_height)
                
        if hasattr(self, 'end_x') and hasattr(self, 'end_y'):
            if self.end_x is not None and device_width:
                result['end_x'] = self.convert_coord_to_relative(self.end_x, device_width)
            if self.end_y is not None and device_height:
                result['end_y'] = self.convert_coord_to_relative(self.end_y, device_height)
                
        # Convert view bounds if they exist
        if hasattr(self, 'view') and self.view and isinstance(self.view, dict) and 'bounds' in self.view:
            view_copy = result['view'] = self.view.copy()
            bounds = self.view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                right, bottom = bounds[1][0], bounds[1][1]
                if device_width and device_height:
                    new_bounds = [
                        [self.convert_coord_to_relative(left, device_width),
                         self.convert_coord_to_relative(top, device_height)],
                        [self.convert_coord_to_relative(right, device_width),
                         self.convert_coord_to_relative(bottom, device_height)]
                    ]
                    view_copy['bounds'] = new_bounds
                    
        # Convert start_view bounds if they exist (SwipeEvent)
        if hasattr(self, 'start_view') and self.start_view and isinstance(self.start_view, dict) and 'bounds' in self.start_view:
            start_view_copy = result['start_view'] = self.start_view.copy()
            bounds = self.start_view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                right, bottom = bounds[1][0], bounds[1][1]
                if device_width and device_height:
                    new_bounds = [
                        [self.convert_coord_to_relative(left, device_width),
                         self.convert_coord_to_relative(top, device_height)],
                        [self.convert_coord_to_relative(right, device_width),
                         self.convert_coord_to_relative(bottom, device_height)]
                    ]
                    start_view_copy['bounds'] = new_bounds
                    
        # Convert end_view bounds if they exist (SwipeEvent)
        if hasattr(self, 'end_view') and self.end_view and isinstance(self.end_view, dict) and 'bounds' in self.end_view:
            end_view_copy = result['end_view'] = self.end_view.copy()
            bounds = self.end_view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                right, bottom = bounds[1][0], bounds[1][1]
                if device_width and device_height:
                    new_bounds = [
                        [self.convert_coord_to_relative(left, device_width),
                         self.convert_coord_to_relative(top, device_height)],
                        [self.convert_coord_to_relative(right, device_width),
                         self.convert_coord_to_relative(bottom, device_height)]
                    ]
                    end_view_copy['bounds'] = new_bounds
                    
        return result

    def to_json(self):
        return json.dumps(self.to_dict())
    
    @staticmethod
    def format_bbox_to_string(bbox):
        """
        Convert bbox to string format
        :param bbox: bbox in tuple (left, top, width, height) or string format
        :return: string format "(left,top,width,height)"
        """
        if bbox is None:
            return "(-1,-1,-1,-1)"
        if isinstance(bbox, tuple) and len(bbox) >= 4:
            return f"({int(bbox[0])},{int(bbox[1])},{int(bbox[2])},{int(bbox[3])})"
        if isinstance(bbox, str):
            return bbox
        return "(-1,-1,-1,-1)"

    @staticmethod
    def convert_coord_to_relative(coord, dimension, scale=1000):
        """
        Convert absolute coordinate to relative coordinate (0-scale)
        :param coord: absolute coordinate value
        :param dimension: screen width or height
        :param scale: target scale (default 1000)
        :return: relative coordinate
        """
        if coord is None or dimension is None or dimension == 0:
            return coord
        return int((coord / dimension) * scale)
    
    @staticmethod
    def format_relative_coord(coord, dimension, scale=1000):
        """
        Format coordinate for display as relative value
        :param coord: absolute coordinate value
        :param dimension: screen width or height  
        :param scale: target scale (default 1000)
        :return: formatted coordinate string
        """
        if coord is None:
            return "-1"
        if dimension is None or dimension == 0:
            return str(int(coord))
        relative = int((coord / dimension) * scale)
        return str(relative)

    def __str__(self):
        return self.to_dict().__str__()

    @abstractmethod
    def send(self, device):
        """
        send this event to device
        :param device: Device
        :return:
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_random_instance(device, app):
        """
        get a random instance of event
        :param device: Device
        :param app: App
        """
        raise NotImplementedError

    @staticmethod
    def from_dict(event_dict):
        if not isinstance(event_dict, dict):
            return None
        if 'event_type' not in event_dict:
            return None
        event_type = event_dict['event_type']
        if event_type == KEY_KeyEvent:
            return KeyEvent(event_dict=event_dict)
        elif event_type == KEY_TouchEvent:
            return TouchEvent(event_dict=event_dict)
        elif event_type == KEY_LongTouchEvent:
            return LongTouchEvent(event_dict=event_dict)
        elif event_type == KEY_SelectEvent or event_type == KEY_UnselectEvent:
            return SelectEvent(event_dict=event_dict)
        elif event_type == KEY_SwipeEvent:
            return SwipeEvent(event_dict=event_dict)
        elif event_type == KEY_ScrollEvent:
            return ScrollEvent(event_dict=event_dict)
        elif event_type == KEY_SetTextEvent:
            return SetTextEvent(event_dict=event_dict)
        elif event_type == KEY_PutTextEvent:
            return PutTextEvent(event_dict=event_dict)
        elif event_type == KEY_IntentEvent:
            return IntentEvent(event_dict=event_dict)
        elif event_type == KEY_ExitEvent:
            return ExitEvent(event_dict=event_dict)
        elif event_type == KEY_SpawnEvent:
            return SpawnEvent(event_dict=event_dict)

    @staticmethod
    def from_event_str(event_str, from_state=None):
        """
        Parse event string back to InputEvent object
        :param event_str: String representation from get_event_str()
        :param from_state: DeviceState object to lookup view information
        :return: InputEvent object or None if parsing fails
        """
        import re
        
        if not isinstance(event_str, str):
            return None
            
        # Extract event class name
        match = re.match(r'^(\w+)\((.*)\)$', event_str.strip())
        if not match:
            return None
            
        event_class_name = match.group(1)
        params_str = match.group(2)
        
        def parse_view_info(params_str, view_prefix="view"):
            """
            Parse view information from parameter string
            :param params_str: Parameters string containing view info
            :param view_prefix: The prefix for the view parameter (e.g., "view", "start_view", "end_view")
            :return: view dict or None
            """
            # Check for None view - using more precise matching
            if re.search(rf'\b{view_prefix}=None\b', params_str):
                return None
                
            # Parse view with format: {prefix}=view_str(activity/class-text)
            view_pattern = rf'{view_prefix}=([^(]+)\(([^/]+)/([^-]+)-([^)]*)\)'
            view_match = re.search(view_pattern, params_str)
            
            if view_match:
                view_str = view_match.group(1)
                activity_short_name = view_match.group(2)
                view_class = view_match.group(3)
                view_text = view_match.group(4)
                
                # First try to find the view in from_state if available
                if from_state is not None:
                    # Search for view by view_str in DeviceState
                    for view_dict in from_state.views:
                        if view_dict.get('view_str') == view_str:
                            # Found the view in state, return the complete view
                            return view_dict
                
            return None
        
        def parse_point_info(params_str, point_prefix="point"):
            """
            Parse point information from parameter string
            :param params_str: Parameters string containing point info
            :param point_prefix: The prefix for the point parameter (e.g., "point", "start_point", "end_point")
            :return: tuple (x, y) or None
            """
            point_pattern = rf'{point_prefix}=\((-?\d+),(-?\d+)\)'
            point_match = re.search(point_pattern, params_str)
            if point_match:
                x, y = int(point_match.group(1)), int(point_match.group(2))
                return (x, y)
            return None
        
        def parse_bbox_info(params_str, bbox_prefix="bbox"):
            """
            Parse bbox information from parameter string
            :param params_str: Parameters string containing bbox info
            :param bbox_prefix: The prefix for the bbox parameter (e.g., "bbox", "start_bbox", "end_bbox")
            :return: tuple (left, top, width, height) or None
            """
            bbox_pattern = rf'{bbox_prefix}=\(([^)]+)\)'
            bbox_match = re.search(bbox_pattern, params_str)
            if bbox_match:
                bbox_content = bbox_match.group(1)
                # Extract numbers from bbox content
                bbox_coords = re.findall(r'(-?\d+)', bbox_content)
                if len(bbox_coords) >= 4:
                    left, top, width, height = map(int, bbox_coords[:4])
                    return (left, top, width, height)
            return None
        
        def parse_duration_info(params_str, duration_prefix="duration"):
            """
            Parse duration information from parameter string
            :param params_str: Parameters string containing duration info
            :param duration_prefix: The prefix for the duration parameter (e.g., "duration")
            :return: int duration in milliseconds or None
            """
            duration_pattern = rf'{duration_prefix}=(\d+)'
            duration_match = re.search(duration_pattern, params_str)
            if duration_match:
                return int(duration_match.group(1))
            return None
        
        def parse_text_info(params_str, text_prefix="text"):
            """
            Parse text information from parameter string
            :param params_str: Parameters string containing text info
            :param text_prefix: The prefix for the text parameter (e.g., "text")
            :return: string text or None
            """
            text_pattern = rf'{text_prefix}=([^),]+)'
            text_match = re.search(text_pattern, params_str)
            if text_match:
                return text_match.group(1)
            return None
        
        def parse_direction_info(params_str, direction_prefix="direction"):
            """
            Parse direction information from parameter string
            :param params_str: Parameters string containing direction info
            :param direction_prefix: The prefix for the direction parameter (e.g., "direction")
            :return: string direction or None
            """
            direction_pattern = rf'{direction_prefix}=([^,)]+)'
            direction_match = re.search(direction_pattern, params_str)
            if direction_match:
                return direction_match.group(1)
            return None
        
        def parse_name_info(params_str, name_prefix="name"):
            """
            Parse name information from parameter string
            :param params_str: Parameters string containing name info
            :param name_prefix: The prefix for the name parameter (e.g., "name")
            :return: string name or None
            """
            name_pattern = rf'{name_prefix}=([^,)]+)'
            name_match = re.search(name_pattern, params_str)
            if name_match:
                return name_match.group(1)
            return None
        
        def parse_type_info(params_str, type_prefix="type"):
            """
            Parse type information from parameter string
            :param params_str: Parameters string containing type info
            :param type_prefix: The prefix for the type parameter (e.g., "type")
            :return: string type or None
            """
            type_pattern = rf'{type_prefix}=([^,)]+)'
            type_match = re.search(type_pattern, params_str)
            if type_match:
                return type_match.group(1)
            return None
        
        try:
            if event_class_name == 'KeyEvent':
                # KeyEvent(name=<name>)
                name = parse_name_info(params_str)
                if name:
                    return KeyEvent(name=name)
                    
            elif event_class_name == 'TouchEvent':
                # TouchEvent(view=<view_info>, point=(<x>,<y>), bbox=((<bbox>)))
                point = parse_point_info(params_str)
                view = parse_view_info(params_str)
                bbox = parse_bbox_info(params_str)
                
                if point:
                    x, y = point
                    return TouchEvent(x=x, y=y, view=view, bbox=bbox)
                    
            elif event_class_name == 'LongTouchEvent':
                # LongTouchEvent(view=<view_info>, point=(<x>,<y>), bbox=((<bbox>)), duration=<duration>)
                point = parse_point_info(params_str)
                duration = parse_duration_info(params_str) or 2000
                view = parse_view_info(params_str)
                bbox = parse_bbox_info(params_str)
                
                if point:
                    x, y = point
                    return LongTouchEvent(x=x, y=y, view=view, bbox=bbox, duration=duration)
                    
            elif event_class_name == 'SwipeEvent':
                # SwipeEvent(start_view=<start_view_info>, start_point=(<start_x>,<start_y>), start_bbox=(<start_bbox>), end_view=<end_view_info>, end_point=(<end_x>,<end_y>), end_bbox=(<end_bbox>), duration=<duration>)
                start_point = parse_point_info(params_str, "start_point")
                end_point = parse_point_info(params_str, "end_point")
                duration = parse_duration_info(params_str) or 1000
                
                # Parse views and bboxes using unified functions
                start_view = parse_view_info(params_str, "start_view")
                end_view = parse_view_info(params_str, "end_view")
                start_bbox = parse_bbox_info(params_str, "start_bbox")
                end_bbox = parse_bbox_info(params_str, "end_bbox")
                
                if start_point and end_point:
                    start_x, start_y = start_point
                    end_x, end_y = end_point
                    return SwipeEvent(start_x=start_x, start_y=start_y, start_view=start_view, start_bbox=start_bbox,
                                    end_x=end_x, end_y=end_y, end_view=end_view, end_bbox=end_bbox, duration=duration)
                    
            elif event_class_name == 'ScrollEvent':
                # ScrollEvent(view=<view_info>, point=(<x>,<y>), bbox=(<bbox>), direction=<direction>)
                point = parse_point_info(params_str)
                direction = parse_direction_info(params_str)
                view = parse_view_info(params_str)
                bbox = parse_bbox_info(params_str)
                
                if direction:
                    x = y = None
                    if point:
                        x, y = point
                        # Handle case where coordinates are (-1, -1)
                        if x == -1 and y == -1:
                            x = y = None
                    return ScrollEvent(x=x, y=y, view=view, bbox=bbox, direction=direction)
                    
            elif event_class_name == 'SetTextEvent':
                # SetTextEvent(view=<view_info>, point=(<x>,<y>), bbox=(<bbox>), text=<text>)
                point = parse_point_info(params_str)
                text = parse_text_info(params_str)
                view = parse_view_info(params_str)
                bbox = parse_bbox_info(params_str)
                
                if point and text:
                    x, y = point
                    return SetTextEvent(x=x, y=y, view=view, bbox=bbox, text=text)
                    
            elif event_class_name == 'PutTextEvent':
                # PutTextEvent(text=<text>)
                text = parse_text_info(params_str)
                if text:
                    return PutTextEvent(text=text)
                    
            elif event_class_name == 'SelectEvent':
                # SelectEvent(type=<event_type>, view=<view_info>) or SelectEvent(type=<event_type>, x=<x>, y=<y>)
                event_type = parse_type_info(params_str)
                if event_type:
                    # Try to extract coordinates
                    coord_match = re.search(r'x=(-?\d+), y=(-?\d+)', params_str)
                    if coord_match:
                        x, y = int(coord_match.group(1)), int(coord_match.group(2))
                        return SelectEvent(event_type=event_type, x=x, y=y)
                    else:
                        # Try to parse view info for SelectEvent
                        view = parse_view_info(params_str)
                        return SelectEvent(event_type=event_type, view=view)
                        
            elif event_class_name == 'IntentEvent':
                # IntentEvent(intent='<intent>')
                intent_match = re.search(r"intent='([^']*)'", params_str)
                if intent_match:
                    intent = intent_match.group(1)
                    return IntentEvent(intent=intent)
                    
            elif event_class_name == 'ManualEvent':
                # ManualEvent(time=<time>)
                time_match = re.search(r'time=([^,)]+)', params_str)
                if time_match:
                    time_val = float(time_match.group(1))
                    event = ManualEvent()
                    event.time = time_val
                    return event
                else:
                    return ManualEvent()
                    
            elif event_class_name == 'ExitEvent':
                # ExitEvent()
                return ExitEvent()
                
            elif event_class_name == 'KillAppEvent':
                # KillAppEvent()
                return KillAppEvent()
                
            elif event_class_name == 'SpawnEvent':
                # SpawnEvent()
                return SpawnEvent()
                
        except (ValueError, AttributeError, IndexError):
            # Return None if any parsing error occurs
            pass
            
        return None

    @abstractmethod
    def get_event_str(self, state):
        pass

    def get_views(self):
        return []


class EventLog(object):
    """
    save an event to local file system
    """

    def __init__(self, device, app, event, profiling_method=None, tag=None):
        self.device = device
        self.app = app
        self.event = event
        if tag is None:
            from datetime import datetime
            tag = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.tag = tag

        self.from_state = None
        self.to_state = None
        self.event_str = None

        self.profiling_method = profiling_method
        self.trace_remote_file = "/data/local/tmp/event.trace"
        self.is_profiling = False
        self.profiling_pid = -1
        self.sampling = None
        # sampling feature was added in Android 5.0 (API level 21)
        if profiling_method is not None and \
           str(profiling_method) != "full" and \
           self.device.get_sdk_version() >= 21:
            self.sampling = int(profiling_method)

    def to_dict(self):
        # Use relative coordinates for event export
        device_width = self.device.get_width() if self.device else None
        device_height = self.device.get_height() if self.device else None
        
        # Try to use to_dict_relative if available, fallback to regular to_dict
        if hasattr(self.event, 'to_dict_relative'):
            event_dict = self.event.to_dict_relative(device_width, device_height)
        else:
            event_dict = self.event.to_dict()
            
        return {
            "tag": self.tag,
            "event": event_dict,
            "start_state": self.from_state.state_str,
            "stop_state": self.to_state.state_str,
            "event_str": self.event_str
        }

    def save2dir(self, output_dir=None):
        # Save event
        if output_dir is None:
            if self.device.output_dir is None:
                return
            else:
                output_dir = os.path.join(self.device.output_dir, "events")
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            event_json_file_path = "%s/event_%s.json" % (output_dir, self.tag)
            event_json_file = open(event_json_file_path, "w")
            json.dump(self.to_dict(), event_json_file, indent=2)
            event_json_file.close()
        except Exception as e:
            self.device.logger.warning("Saving event to dir failed.")
            self.device.logger.warning(e)

    def save_views(self, output_dir=None):
        # Save views
        views = self.event.get_views()
        if views:
            for view_dict in views:
                self.from_state.save_view_img(view_dict=view_dict, output_dir=output_dir)

    def is_start_event(self):
        if isinstance(self.event, IntentEvent):
            intent_cmd = self.event.intent
            if "start" in intent_cmd and self.app.get_package_name() in intent_cmd:
                return True
        return False

    def start(self):
        """
        start sending event
        """
        self.from_state = self.device.get_current_state()
        self.start_profiling()
        self.event_str = self.event.get_event_str(self.from_state)
        print("Action: %s" % self.event_str)
        self.device.send_event(self.event)

    def start_profiling(self):
        """
        start profiling the current event
        @return:
        """
        if self.profiling_method is None:
            return
        if self.is_profiling:
            return
        pid = self.device.get_app_pid(self.app)
        if pid is None:
            if self.is_start_event():
                start_intent = self.app.get_start_with_profiling_intent(self.trace_remote_file, self.sampling)
                self.event.intent = start_intent.get_cmd()
                self.is_profiling = True
            return
        if self.sampling is not None:
            self.device.adb.shell(
                ["am", "profile", "start", "--sampling", str(self.sampling), str(pid), self.trace_remote_file])
        else:
            self.device.adb.shell(["am", "profile", "start", str(pid), self.trace_remote_file])
        self.is_profiling = True
        self.profiling_pid = pid

    def stop(self):
        """
        finish sending event
        """
        self.stop_profiling()
        self.to_state = self.device.get_current_state()
        self.save2dir()
        self.save_views()

    def stop_profiling(self, output_dir=None):
        if self.profiling_method is None:
            return
        if not self.is_profiling:
            return
        try:
            if self.profiling_pid == -1:
                pid = self.device.get_app_pid(self.app)
                if pid is None:
                    return
                self.profiling_pid = pid

            self.device.adb.shell(["am", "profile", "stop", str(self.profiling_pid)])
            if self.sampling is None:
                time.sleep(3)  # guess this time can vary between machines

            if output_dir is None:
                if self.device.output_dir is None:
                    return
                else:
                    output_dir = os.path.join(self.device.output_dir, "events")
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            event_trace_local_path = "%s/event_trace_%s.trace" % (output_dir, self.tag)
            self.device.pull_file(self.trace_remote_file, event_trace_local_path)

        except Exception as e:
            self.device.logger.warning("profiling event failed")
            self.device.logger.warning(e)


class ManualEvent(InputEvent):
    """
    a manual event
    """

    def __init__(self, event_dict=None):
        super().__init__()
        self.event_type = KEY_ManualEvent
        self.time = time.time()
        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        return None

    def send(self, device):
        # do nothing
        pass

    def get_event_str(self, state):
        return "%s(time=%s)" % (self.__class__.__name__, self.time)


class ExitEvent(InputEvent):
    """
    an event to stop testing
    """

    def __init__(self, event_dict=None):
        super().__init__()
        self.event_type = KEY_ExitEvent
        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        return None

    def send(self, device):
        # device.disconnect()
        raise KeyboardInterrupt()

    def get_event_str(self, state):
        return "%s()" % self.__class__.__name__


class KillAppEvent(InputEvent):
    """
    an event to stop testing
    """

    def __init__(self, app=None, event_dict=None):
        super().__init__()
        self.event_type = KEY_KillAppEvent
        self.stop_intent = None
        if app:
            self.stop_intent = app.get_stop_intent().get_cmd()
        elif event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        return None

    def send(self, device):
        if self.stop_intent:
            device.send_intent(self.stop_intent)
        device.key_press('HOME')

    def get_event_str(self, state):
        return "%s()" % self.__class__.__name__


class KeyEvent(InputEvent):
    """
    a key pressing event
    """

    def __init__(self, name=None, event_dict=None):
        super().__init__()
        self.event_type = KEY_KeyEvent
        self.name = name
        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        key_name = random.choice(POSSIBLE_KEYS)
        return KeyEvent(key_name)

    def send(self, device):
        device.key_press(self.name)
        return True

    def get_event_str(self, state):
        return "%s(name=%s)" % (self.__class__.__name__, self.name)


class UIEvent(InputEvent):
    """
    This class describes a UI event of app, such as touch, click, etc
    """
    def __init__(self):
        super().__init__()

    def send(self, device):
        raise NotImplementedError

    @staticmethod
    def get_random_instance(device, app):
        if not device.is_foreground(app):
            # if current app is in background, bring it to foreground
            component = app.get_package_name()
            if app.get_main_activity():
                component += "/%s" % app.get_main_activity()
            return IntentEvent(Intent(suffix=component))

        else:
            choices = {
                TouchEvent: 6,
                LongTouchEvent: 2,
                SwipeEvent: 2
            }
            event_type = utils.weighted_choice(choices)
            return event_type.get_random_instance(device, app)

    @staticmethod
    def get_xy(x, y, view):
        if x and y:
            return x, y
        if view:
            from .device_state import DeviceState
            return DeviceState.get_view_center(view_dict=view)
        return x, y

    @staticmethod
    def view_str(state, view):
        view_class = view['class'].split('.')[-1]
        view_text = view['text'].replace('\n', '\\n') if 'text' in view and view['text'] else ''
        view_text = view_text[:10] if len(view_text) > 10 else view_text
        view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
        return f"state={state.state_str}, view={view['view_str']}({view_short_sig})"


class TouchEvent(UIEvent):
    """
    a touch on screen
    """

    def __init__(self, x=None, y=None, view=None, bbox=None, event_dict=None):
        super().__init__()
        self.event_type = KEY_TouchEvent
        self.x = x
        self.y = y
        self.view = view
        self.bbox = bbox
        if bbox is None and view is not None and 'bounds' in view:
            bounds = view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                width = bounds[1][0] - bounds[0][0]
                height = bounds[1][1] - bounds[0][1]
                self.bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        x = random.uniform(0, device.get_width())
        y = random.uniform(0, device.get_height())
        return TouchEvent(x, y)

    def send(self, device):
        x, y = UIEvent.get_xy(x=self.x, y=self.y, view=self.view)
        device.view_long_touch(x=x, y=y, duration=200)
        return True

    def get_event_str(self, state):
        # Use absolute coordinates
        abs_x = int(self.x) if self.x is not None else -1
        abs_y = int(self.y) if self.y is not None else -1
        point = f"({abs_x},{abs_y})"
        
        # Priority: use existing bbox first, then calculate from view, finally use default
        if self.bbox is not None:
            bbox = self.format_bbox_to_string(self.bbox)
        elif self.view is not None:
            bounds = self.view['bounds']
            left, top = bounds[0][0], bounds[0][1]
            width = bounds[1][0] - bounds[0][0] 
            height = bounds[1][1] - bounds[0][1]
            # Use absolute bbox coordinates
            bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        else:
            bbox = "(-1,-1,-1,-1)"
        
        if self.view is not None:
            view_class = self.view['class'].split('.')[-1]
            view_text = self.view['text'].replace('\n', '\\n') if 'text' in self.view and self.view['text'] else ''
            view_text = view_text[:10] if len(view_text) > 10 else view_text
            view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
            view_info = f"{self.view['view_str']}({view_short_sig})"
        else:
            view_info="None"
        return f"{self.__class__.__name__}(view={view_info}, point={point}, bbox=({bbox}))"

    def get_views(self):
        return [self.view] if self.view else []


class SelectEvent(UIEvent):
    """
    select a checkbox
    """

    def __init__(self, event_type=KEY_SelectEvent, x=None, y=None, view=None, event_dict=None):
        super().__init__()
        self.event_type = event_type
        self.x = x
        self.y = y
        self.view = view
        if event_dict is not None:
            self.__dict__.update(event_dict)

    def send(self, device):
        x, y = UIEvent.get_xy(x=self.x, y=self.y, view=self.view)
        if 'special_attr' in self.view:
            if self.event_type == KEY_UnselectEvent and 'selected' in self.view['special_attr']:
                device.view_long_touch(x=x, y=y, duration=200)
            elif self.event_type == KEY_SelectEvent and 'selected' not in self.view['special_attr']:
                device.view_long_touch(x=x, y=y, duration=200)
        else:
            device.view_long_touch(x=x, y=y, duration=200)
        return True

    def get_event_str(self, state):
        if self.view is not None:
            view_class = self.view['class'].split('.')[-1]
            view_text = self.view['text'].replace('\n', '\\n') if 'text' in self.view and self.view['text'] else ''
            view_text = view_text[:10] if len(view_text) > 10 else view_text
            view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
            view_info = f"view={self.view['view_str']}({view_short_sig})"
            return f"{self.__class__.__name__}(type={self.event_type}, {view_info})"
        elif self.x is not None and self.y is not None:
            return "%s(type=%s, x=%s, y=%s)" % (self.__class__.__name__, self.event_type, self.x, self.y)
        else:
            msg = "Invalid %s!" % self.__class__.__name__
            raise InvalidEventException(msg)

    def get_views(self):
        return [self.view] if self.view else []


class LongTouchEvent(UIEvent):
    """
    a long touch on screen
    """

    def __init__(self, x=None, y=None, view=None, bbox=None, duration=2000, event_dict=None):
        super().__init__()
        self.event_type = KEY_LongTouchEvent
        self.x = x
        self.y = y
        self.view = view
        self.bbox = bbox
        self.duration = duration
        if bbox is None and view is not None and 'bounds' in view:
            bounds = view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                width = bounds[1][0] - bounds[0][0]
                height = bounds[1][1] - bounds[0][1]
                self.bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        x = random.uniform(0, device.get_width())
        y = random.uniform(0, device.get_height())
        return LongTouchEvent(x, y)

    def send(self, device):
        x, y = UIEvent.get_xy(x=self.x, y=self.y, view=self.view)
        device.view_long_touch(x=x, y=y, duration=self.duration)
        return True

    def get_event_str(self, state):
        # Use absolute coordinates
        abs_x = int(self.x) if self.x is not None else -1
        abs_y = int(self.y) if self.y is not None else -1
        point = f"({abs_x},{abs_y})"
        duration_ms = getattr(self, 'duration', 2000)
        
        # Priority: use existing bbox first, then calculate from view, finally use default
        if self.bbox is not None:
            bbox = self.format_bbox_to_string(self.bbox)
        elif self.view is not None:
            bounds = self.view['bounds']
            left, top = bounds[0][0], bounds[0][1]
            width = bounds[1][0] - bounds[0][0] 
            height = bounds[1][1] - bounds[0][1]
            # Use absolute bbox coordinates
            bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        else:
            bbox = "(-1,-1,-1,-1)"
        
        if self.view is not None:
            view_class = self.view['class'].split('.')[-1]
            view_text = self.view['text'].replace('\n', '\\n') if 'text' in self.view and self.view['text'] else ''
            view_text = view_text[:10] if len(view_text) > 10 else view_text
            view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
            view_info = f"{self.view['view_str']}({view_short_sig})"
        else:
            view_info="None"
        return f"{self.__class__.__name__}(view={view_info}, point={point}, bbox=({bbox}), duration={duration_ms})"

    def get_views(self):
        return [self.view] if self.view else []


class SwipeEvent(UIEvent):
    """
    a drag gesture on screen
    """

    def __init__(self, start_x=None, start_y=None, start_view=None, start_bbox=None, end_x=None, end_y=None, end_view=None, end_bbox=None,
                 duration=1000, event_dict=None):
        super().__init__()
        self.event_type = KEY_SwipeEvent

        self.start_x = start_x
        self.start_y = start_y
        self.start_view = start_view
        self.start_bbox = start_bbox

        self.end_x = end_x
        self.end_y = end_y
        self.end_view = end_view
        self.end_bbox = end_bbox

        self.duration = duration

        if start_bbox is None and start_view is not None and 'bounds' in start_view:
            bounds = start_view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                width = bounds[1][0] - bounds[0][0]
                height = bounds[1][1] - bounds[0][1]
                self.start_bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"

        if end_bbox is None and end_view is not None and 'bounds' in end_view:
            bounds = end_view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                width = bounds[1][0] - bounds[0][0]
                height = bounds[1][1] - bounds[0][1]
                self.end_bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"

        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        start_x = random.uniform(0, device.get_width())
        start_y = random.uniform(0, device.get_height())
        end_x = random.uniform(0, device.get_width())
        end_y = random.uniform(0, device.get_height())
        return SwipeEvent(start_x=start_x, start_y=start_y,
                          end_x=end_x, end_y=end_y)

    def send(self, device):
        start_x, start_y = UIEvent.get_xy(x=self.start_x, y=self.start_y, view=self.start_view)
        end_x, end_y = UIEvent.get_xy(x=self.end_x, y=self.end_y, view=self.end_view)
        device.view_drag((start_x, start_y), (end_x, end_y), self.duration)
        return True

    def get_event_str(self, state):
        # Use absolute start coordinates
        abs_start_x = int(self.start_x) if self.start_x is not None else -1
        abs_start_y = int(self.start_y) if self.start_y is not None else -1
        start_point = f"({abs_start_x},{abs_start_y})"
        
        # Priority: use existing start_bbox first, then calculate from start_view, finally use default
        if self.start_bbox is not None:
            start_bbox = self.format_bbox_to_string(self.start_bbox)
        elif self.start_view is not None:
            bounds = self.start_view['bounds']
            left, top = bounds[0][0], bounds[0][1]
            width = bounds[1][0] - bounds[0][0] 
            height = bounds[1][1] - bounds[0][1]
            # Use absolute start bbox coordinates
            start_bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        else:
            start_bbox = "(-1,-1,-1,-1)"
        
        if self.start_view is not None:
            view_class = self.start_view['class'].split('.')[-1]
            view_text = self.start_view['text'].replace('\n', '\\n') if 'text' in self.start_view and self.start_view['text'] else ''
            view_text = view_text[:10] if len(view_text) > 10 else view_text
            view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
            start_view_info = f"{self.start_view['view_str']}({view_short_sig})"
        else:
            start_view_info = "None"

        # Use absolute end coordinates
        abs_end_x = int(self.end_x) if self.end_x is not None else -1
        abs_end_y = int(self.end_y) if self.end_y is not None else -1
        end_point = f"({abs_end_x},{abs_end_y})"
        
        # Priority: use existing end_bbox first, then calculate from end_view, finally use default
        if self.end_bbox is not None:
            end_bbox = self.format_bbox_to_string(self.end_bbox)
        elif self.end_view is not None:
            bounds = self.end_view['bounds']
            left, top = bounds[0][0], bounds[0][1]
            width = bounds[1][0] - bounds[0][0] 
            height = bounds[1][1] - bounds[0][1]
            # Use absolute end bbox coordinates
            end_bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        else:
            end_bbox = "(-1,-1,-1,-1)"
        
        if self.end_view is not None:
            view_class = self.end_view['class'].split('.')[-1]
            view_text = self.end_view['text'].replace('\n', '\\n') if 'text' in self.end_view and self.end_view['text'] else ''
            view_text = view_text[:10] if len(view_text) > 10 else view_text
            view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
            end_view_info = f"{self.end_view['view_str']}({view_short_sig})"
        else:
            end_view_info = "None"

        return f"{self.__class__.__name__}(start_view={start_view_info}, start_point={start_point}, start_bbox=({start_bbox}), end_view={end_view_info}, end_point={end_point}, end_bbox=({end_bbox}), duration={self.duration})"

    def get_views(self):
        views = []
        if self.start_view:
            views.append(self.start_view)
        if self.end_view:
            views.append(self.end_view)
        return views


class ScrollEvent(UIEvent):
    """
    swipe gesture
    """

    def __init__(self, x=None, y=None, view=None, bbox=None, direction="down", event_dict=None):
        super().__init__()
        self.event_type = KEY_ScrollEvent
        self.x = x
        self.y = y
        self.view = view
        self.bbox = bbox
        self.direction = direction

        if bbox is None and view is not None and 'bounds' in view:
            bounds = view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                width = bounds[1][0] - bounds[0][0]
                height = bounds[1][1] - bounds[0][1]
                self.bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"

        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        x = random.uniform(0, device.get_width())
        y = random.uniform(0, device.get_height())
        direction = random.choice(["up", "down", "left", "right"])
        return ScrollEvent(x, y, direction)

    def send(self, device):
        if self.view is not None:
            from .device_state import DeviceState
            width = DeviceState.get_view_width(view_dict=self.view)
            height = DeviceState.get_view_height(view_dict=self.view)
        else:
            width = device.get_width()
            height = device.get_height()

        x, y = UIEvent.get_xy(x=self.x, y=self.y, view=self.view)
        if not x or not y:
            # If no view and no coordinate specified, use the screen center coordinate
            x = width / 2
            y = height / 2

        start_x, start_y = x, y
        end_x, end_y = x, y
        duration = 500

        if self.direction == "UP":
            start_y -= height * 2 / 5
            end_y += height * 2 / 5
        elif self.direction == "DOWN":
            start_y += height * 2 / 5
            end_y -= height * 2 / 5
        elif self.direction == "LEFT":
            start_x -= width * 2 / 5
            end_x += width * 2 / 5
        elif self.direction == "RIGHT":
            start_x += width * 2 / 5
            end_x -= width * 2 / 5

        device.view_drag((start_x, start_y), (end_x, end_y), duration)
        return True

    def get_event_str(self, state):
        # Use absolute coordinates
        if (self.x is None or self.y is None) or (self.x == -1 and self.y == -1):
            point = "(-1,-1)"
        else:
            abs_x = int(self.x)
            abs_y = int(self.y)
            point = f"({abs_x},{abs_y})"
        
        # Priority: use existing bbox first, then calculate from view, finally use default
        if self.bbox is not None:
            bbox = self.format_bbox_to_string(self.bbox)
        elif self.view is not None:
            bounds = self.view['bounds']
            left, top = bounds[0][0], bounds[0][1]
            width = bounds[1][0] - bounds[0][0] 
            height = bounds[1][1] - bounds[0][1]
            # Use absolute bbox coordinates
            bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        else:
            bbox = "(-1,-1,-1,-1)"
        
        if self.view is not None:
            view_class = self.view['class'].split('.')[-1]
            view_text = self.view['text'].replace('\n', '\\n') if 'text' in self.view and self.view['text'] else ''
            view_text = view_text[:10] if len(view_text) > 10 else view_text
            view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
            view_info = f"{self.view['view_str']}({view_short_sig})"
        else:
            view_info = "None"

        return f"{self.__class__.__name__}(view={view_info}, point={point}, bbox=({bbox}), direction={self.direction})"

    def get_views(self):
        return [self.view] if self.view else []


class SetTextEvent(UIEvent):
    """
    input text to target UI
    """

    @staticmethod
    def get_random_instance(device, app):
        pass

    def __init__(self, x=None, y=None, view=None, bbox=None, text=None, event_dict=None):
        super().__init__()
        self.event_type = KEY_SetTextEvent
        self.x = x
        self.y = y
        self.view = view
        self.bbox = bbox
        self.text = text
        if bbox is None and view is not None and 'bounds' in view:
            bounds = view['bounds']
            if bounds and len(bounds) >= 2 and len(bounds[0]) >= 2 and len(bounds[1]) >= 2:
                left, top = bounds[0][0], bounds[0][1]
                width = bounds[1][0] - bounds[0][0]
                height = bounds[1][1] - bounds[0][1]
                self.bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        if event_dict is not None:
            self.__dict__.update(event_dict)

    def send(self, device):
        x, y = UIEvent.get_xy(x=self.x, y=self.y, view=self.view)
        touch_event = TouchEvent(x=x, y=y)
        touch_event.send(device)
        device.view_set_text(self.text)
        return True

    def get_event_str(self, state):
        # Use absolute coordinates
        abs_x = int(self.x) if self.x is not None else -1
        abs_y = int(self.y) if self.y is not None else -1
        point = f"({abs_x},{abs_y})"
        
        # Priority: use existing bbox first, then calculate from view, finally use default
        if self.bbox is not None:
            bbox = self.format_bbox_to_string(self.bbox)
        elif self.view is not None:
            bounds = self.view['bounds']
            left, top = bounds[0][0], bounds[0][1]
            width = bounds[1][0] - bounds[0][0] 
            height = bounds[1][1] - bounds[0][1]
            # Use absolute bbox coordinates
            bbox = f"({int(left)},{int(top)},{int(width)},{int(height)})"
        else:
            bbox = "(-1,-1,-1,-1)"
        
        if self.view is not None:
            view_class = self.view['class'].split('.')[-1]
            view_text = self.view['text'].replace('\n', '\\n') if 'text' in self.view and self.view['text'] else ''
            view_text = view_text[:10] if len(view_text) > 10 else view_text
            view_short_sig = f'{state.activity_short_name}/{view_class}-{view_text}'
            view_info = f"{self.view['view_str']}({view_short_sig})"
        else:
            view_info = "None"

        return f"{self.__class__.__name__}(view={view_info}, point={point}, bbox=({bbox}), text={self.text})"

    def get_views(self):
        return [self.view] if self.view else []


class PutTextEvent(InputEvent):
    """
    input text without targeting a specific UI element
    This is useful for typing text into the currently focused input field
    """

    @staticmethod
    def get_random_instance(device, app):
        pass

    def __init__(self, text=None, event_dict=None):
        super().__init__()
        self.event_type = KEY_PutTextEvent
        self.text = text
        if event_dict is not None:
            self.__dict__.update(event_dict)

    def send(self, device):
        device.view_set_text(self.text)
        return True

    def get_event_str(self, state):
        return f"{self.__class__.__name__}(text={self.text})"

    def get_views(self):
        return []


class DummyIntent:
    """
    A dummy intent object that returns an empty command for manual mode
    """
    def __init__(self, cmd=""):
        self.cmd = cmd
        self.event_type = 'intent'
    
    def get_cmd(self):
        return self.cmd


class IntentEvent(InputEvent):
    """
    An event describing an intent
    """

    def __init__(self, intent=None, event_dict=None):
        super().__init__()
        self.event_type = KEY_IntentEvent
        if event_dict is not None:
            intent = event_dict['intent']
        if isinstance(intent, Intent):
            self.intent = intent.get_cmd()
        elif isinstance(intent, str):
            self.intent = intent
        else:
            msg = "intent must be either an instance of Intent or a string."
            raise InvalidEventException(msg)
        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        pass

    def send(self, device):
        device.send_intent(intent=self.intent)
        return True

    def get_event_str(self, state):
        return "%s(intent='%s')" % (self.__class__.__name__, self.intent)


class SpawnEvent(InputEvent):
    """
    An event to spawn then stop testing
    """

    def __init__(self, event_dict=None):
        super().__init__()
        self.event_type = KEY_SpawnEvent
        if event_dict is not None:
            self.__dict__.update(event_dict)

    @staticmethod
    def get_random_instance(device, app):
        return None

    def send(self, device):
        master = self.__dict__["master"]
        # force touch the view
        init_script = {
            "views": {
                "droid_master_view": {
                    "resource_id": self.__dict__["view"]["resource_id"],
                    "class": self.__dict__["view"]["class"],
                }
            },
            "states": {
                "droid_master_state": {
                    "views": ["droid_master_view"]
                }
            },
            "operations": {
                "droid_master_operation": [
                    {
                        "event_type": "touch",
                        "target_view": "droid_master_view"
                    }
                ]
            },
            "main": {
                "droid_master_state": ["droid_master_operation"]
            }
        }
        init_script_json = json.dumps(init_script, indent=2)
        import xmlrpc.client
        proxy = xmlrpc.client.ServerProxy(master)
        proxy.spawn(device.serial, init_script_json)

    def get_event_str(self, state):
        return "%s()" % self.__class__.__name__


EVENT_TYPES = {
    KEY_KeyEvent: KeyEvent,
    KEY_TouchEvent: TouchEvent,
    KEY_LongTouchEvent: LongTouchEvent,
    KEY_SwipeEvent: SwipeEvent,
    KEY_ScrollEvent: ScrollEvent,
    KEY_SetTextEvent: SetTextEvent,
    KEY_PutTextEvent: PutTextEvent,
    KEY_IntentEvent: IntentEvent,
    KEY_SpawnEvent: SpawnEvent
}
