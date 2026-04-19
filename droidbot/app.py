import logging
import os
import re
import subprocess
from .intent import Intent
from .input_event import DummyIntent


class App(object):
    """
    this class describes an app
    """

    def __init__(self, app_path, output_dir=None):
        """
        create an App instance
        :param app_path: local file path of app
        :return:
        """
        assert app_path is not None
        self.logger = logging.getLogger(self.__class__.__name__)

        self.app_path = app_path

        self.output_dir = output_dir
        if output_dir is not None:
            if not os.path.isdir(output_dir):
                os.makedirs(output_dir)

        from androguard.core.apk import APK
        self.apk = APK(self.app_path)
        self.package_name = self.apk.get_package()
        self.app_name = self.apk.get_app_name()
        self.main_activity = self.apk.get_main_activity()
        self.permissions = self.apk.get_permissions()
        self.activities = self.apk.get_activities()
        self.possible_broadcasts = self.get_possible_broadcasts()
        self.dumpsys_main_activity = None
        self.signature = self.get_signature()

    def get_package_name(self):
        """
        get package name of current app
        :return:
        """
        return self.package_name

    def get_main_activity(self):
        """
        get package name of current app
        :return:
        """
        if self.main_activity is not None:
            return self.main_activity
        else:
            self.logger.warning("Cannot get main activity from manifest. Using dumpsys result instead.")
            return self.dumpsys_main_activity

    def get_start_intent(self):
        """
        get an intent to start the app
        :return: Intent
        """
        package_name = self.get_package_name()
        if self.get_main_activity():
            package_name += "/%s" % self.get_main_activity()
        return Intent(suffix=package_name)

    def get_start_with_profiling_intent(self, trace_file, sampling=None):
        """
        get an intent to start the app with profiling
        :return: Intent
        """
        package_name = self.get_package_name()
        if self.get_main_activity():
            package_name += "/%s" % self.get_main_activity()
        if sampling is not None:
            return Intent(prefix="start --start-profiler %s --sampling %d" % (trace_file, sampling), suffix=package_name)
        else:
            return Intent(prefix="start --start-profiler %s" % trace_file, suffix=package_name)

    def get_stop_intent(self):
        """
        get an intent to stop the app
        :return: Intent
        """
        package_name = self.get_package_name()
        return Intent(prefix="force-stop", suffix=package_name)

    def get_possible_broadcasts(self):
        possible_broadcasts = set()
        for receiver in self.apk.get_receivers():
            intent_filters = self.apk.get_intent_filters('receiver', receiver)
            actions = intent_filters['action'] if 'action' in intent_filters else []
            categories = intent_filters['category'] if 'category' in intent_filters else []
            categories.append(None)
            for action in actions:
                for category in categories:
                    intent = Intent(prefix='broadcast', action=action, category=category)
                    possible_broadcasts.add(intent)
        return possible_broadcasts

    def get_signature(self):
        """
        get signature of current app
        :return:
        """
        try:
            from hashlib import sha256
            signature = sha256(self.apk.get_signature()).hexdigest()
            return ':'.join(signature[i:i+2].upper() for i in range(0, len(signature), 2))
        except Exception:
            # Fallback to signature name if any error occurs
            return self.apk.get_signature_name()


class DummyApp:
    """
    A dummy app object for manual policy when no specific app is targeted
    """
    def __init__(self):
        self.package_name = "system.manual.mode"
        self.main_activity = None
        self.activities = []  # Empty list for UTG compatibility
        self.signature = "dummy_signature"  # Dummy signature for UTG
        self.app_name = "Manual Mode (No App)"
        self.permissions = []
        self.possible_broadcasts = set()
        
    def get_package_name(self):
        return self.package_name
        
    def get_main_activity(self):
        return self.main_activity
        
    def get_start_intent(self):
        # Return DummyIntent for dummy app - no specific app to start
        return DummyIntent("")
        
    def get_stop_intent(self):
        # Return DummyIntent for dummy app - no specific app to stop  
        return DummyIntent("")
        
    def get_start_with_profiling_intent(self, trace_file, sampling=None):
        # Return DummyIntent for dummy app - no profiling needed
        # Parameters are unused as this is a dummy implementation
        return DummyIntent("")
        
    def get_signature(self):
        return self.signature


class InstalledApp(object):
    """
    this class describes an installed app by parsing dumpsys package output
    """

    def __init__(self, package_name, device=None):
        """
        create an InstalledApp instance by package name
        :param package_name: package name of the installed app
        :param device: device instance for executing dumpsys command  
        :return:
        """
        assert package_name is not None
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.package_name = package_name
        self.device = device
        
        # Initialize attributes with None/empty values
        self.app_name = None
        self.main_activity = None
        self.permissions = []
        self.activities = []
        self.possible_broadcasts = set()
        self.dumpsys_main_activity = None
        self.signature = None
        
        # Set app_path to package_name for compatibility with App class interface
        self.app_path = package_name
        
        # Parse dumpsys output to populate attributes
        self._parse_dumpsys_output()

    def _execute_dumpsys_command(self):
        """
        Execute dumpsys package command for the package
        :return: dumpsys output string
        """
        try:
            if self.device:
                # Use device's adb connection if available
                cmd = f"dumpsys package {self.package_name}"
                result = self.device.adb.shell(cmd)
                return result if result else ""
            else:
                # Use subprocess for direct adb call
                cmd = ["adb", "shell", "dumpsys", "package", self.package_name]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return result.stdout if result.returncode == 0 else ""
        except Exception as e:
            self.logger.error(f"Failed to execute dumpsys command: {e}")
            return ""

    def _parse_dumpsys_output(self):
        """
        Parse dumpsys package output to extract app information
        """
        dumpsys_output = self._execute_dumpsys_command()
        if not dumpsys_output:
            self.logger.warning(f"No dumpsys output for package {self.package_name}")
            return
            
        self._parse_basic_info(dumpsys_output)
        self._parse_activities(dumpsys_output)
        self._parse_permissions(dumpsys_output)
        self._parse_receivers(dumpsys_output)
        self._parse_signature(dumpsys_output)

    def _parse_basic_info(self, dumpsys_output):
        """
        Parse basic package information from dumpsys output
        """
        lines = dumpsys_output.split('\n')
        
        for i, line in enumerate(lines):
            # Find main activity from Activity Resolver Table
            if "android.intent.action.MAIN:" in line:
                # Look for the next few lines to find the activity with LAUNCHER category
                for j in range(i + 1, min(i + 10, len(lines))):
                    next_line = lines[j].strip()
                    if "Category: \"android.intent.category.LAUNCHER\"" in next_line:
                        # Look backwards to find the activity name
                        for k in range(j - 1, max(j - 10, 0), -1):
                            prev_line = lines[k].strip()
                            if self.package_name in prev_line and "filter" in prev_line:
                                activity_match = re.search(rf'{re.escape(self.package_name)}/([^\s]+)', prev_line)
                                if activity_match:
                                    # 保持完整的活动名称格式 com.sankuai.meituan.takeoutnew/.ui.page.boot.WelcomeActivity
                                    self.main_activity = activity_match.group(1)
                                    break
                        break
            
            # Parse package section for more details
            if f"Package [{self.package_name}]" in line:
                # Parse version name
                for j in range(i + 1, min(i + 20, len(lines))):
                    version_line = lines[j].strip()
                    if "versionName=" in version_line:
                        version_match = re.search(r'versionName=([^\s]+)', version_line)
                        if version_match:
                            self.app_name = version_match.group(1)
                        break

    def _parse_activities(self, dumpsys_output):
        """
        Parse activities from Activity Resolver Table
        """
        lines = dumpsys_output.split('\n')
        in_activity_section = False
        
        for line in lines:
            if "Activity Resolver Table:" in line:
                in_activity_section = True
                continue
            elif "Receiver Resolver Table:" in line or "Service Resolver Table:" in line:
                in_activity_section = False
                continue
                
            if in_activity_section and self.package_name in line:
                # Extract activity name from lines like: 
                # "91d7adf com.sankuai.meituan.takeoutnew/.dcep.PayRouteActivity filter 477732c"
                activity_match = re.search(rf'{re.escape(self.package_name)}/([^\s]+)', line)
                if activity_match:
                    # 保持完整的活动名称格式 com.sankuai.meituan.takeoutnew/.ui.page.boot.WelcomeActivity
                    activity = f"{self.package_name}/{activity_match.group(1)}"
                    if activity not in self.activities:
                        self.activities.append(activity)

    def _parse_permissions(self, dumpsys_output):
        """
        Parse requested permissions from dumpsys output
        """
        lines = dumpsys_output.split('\n')
        in_requested_permissions = False
        
        for line in lines:
            line = line.strip()
            if "requested permissions:" in line:
                in_requested_permissions = True
                continue
            elif in_requested_permissions:
                if line.startswith("install permissions:") or line.startswith("User "):
                    break
                elif line and not line.startswith("android.permission") and not line.startswith("com."):
                    break
                elif line:
                    self.permissions.append(line)

    def _parse_receivers(self, dumpsys_output):
        """
        Parse broadcast receivers and create possible broadcast intents
        """
        lines = dumpsys_output.split('\n')
        in_receiver_section = False
        
        for line in lines:
            if "Receiver Resolver Table:" in line:
                in_receiver_section = True
                continue
            elif "Service Resolver Table:" in line:
                in_receiver_section = False
                continue
                
            if in_receiver_section:
                line = line.strip()
                if f"Action:" in line and '"' in line:
                    # Extract action from: Action: "com.dianping.dpmtpush.RECEIVE_PASS_THROUGH_MESSAGE"
                    action_match = re.search(r'Action:\s*"([^"]+)"', line)
                    if action_match:
                        action = action_match.group(1)
                        intent = Intent(prefix='broadcast', action=action)
                        self.possible_broadcasts.add(intent)

    def _parse_signature(self, dumpsys_output):
        """
        Parse app signature from dumpsys output
        """
        lines = dumpsys_output.split('\n')
        
        # Look for the actual signature content in the format:
        # Signatures: [73:A6:11:C3:A0:1D:C6:E1:13:88:87:3D:AE:EE:1E:55:6A:D9:E5:76:8E:5C:22:20:55:F5:08:A2:4C:3A:82:15]
        for line in lines:
            if "Signatures: [" in line and ":" in line:
                # Extract full signature content
                sig_match = re.search(r'Signatures:\s*\[([A-F0-9:]+)\]', line)
                if sig_match:
                    self.signature = sig_match.group(1)
                    break
            elif "signatures=PackageSignatures" in line:
                # Also check for alternative format like: signatures=PackageSignatures{137d057 version:2, signatures:[c6acad1f]}
                alt_match = re.search(r'signatures:\[([a-f0-9]+)\]', line)
                if alt_match:
                    # Convert short form to full form if needed
                    short_sig = alt_match.group(1)
                    self.signature = short_sig
                    break

    def get_package_name(self):
        """
        get package name of current app
        :return:
        """
        return self.package_name

    def get_main_activity(self):
        """
        get main activity of current app
        :return:
        """
        if self.main_activity is not None:
            return self.main_activity
        else:
            self.logger.warning("Cannot get main activity from dumpsys.")
            return self.dumpsys_main_activity

    def get_start_intent(self):
        """
        get an intent to start the app
        :return: Intent
        """
        package_name = self.get_package_name()
        if self.get_main_activity():
            package_name += "/%s" % self.get_main_activity()
        return Intent(suffix=package_name)

    def get_stop_intent(self):
        """
        get an intent to stop the app
        :return: Intent
        """
        package_name = self.get_package_name()
        return Intent(prefix="force-stop", suffix=package_name)

    def get_possible_broadcasts(self):
        """
        get possible broadcast intents for this app
        :return: set of Intent objects
        """
        return self.possible_broadcasts

    def get_signature(self):
        """
        get signature of current app
        :return:
        """
        return self.signature
    
