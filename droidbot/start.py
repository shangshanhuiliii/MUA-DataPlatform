# helper file of droidbot
# it parses command arguments and send the options to droidbot
import argparse
import questionary
from . import input_manager
from . import input_policy
from . import env_manager
from . import utils
from .droidbot import DroidBot
from .droidmaster import DroidMaster
from .device import Device


def select_device():
    """
    List available devices and let user select one
    :return: selected device serial number, or None if no device available or not selected
    """
    try:
        print("Getting available devices...")
        available_devices = utils.get_available_devices()
        
        if not available_devices:
            print("No devices found. Please make sure your device is connected and USB debugging is enabled.")
            return None
        
        if len(available_devices) == 1:
            print(f"Only one device found: {available_devices[0]}")
            return available_devices[0]
        
        print(f"Found {len(available_devices)} devices")
        
        # Create choices for questionary with device info
        choices = []
        for device_serial in available_devices:
            try:
                # Try to get device model for better display
                device = Device(device_serial=device_serial)
                model = device.adb.get_property("ro.product.model")
                choices.append(f"{device_serial} ({model})")
            except Exception:
                # Fallback to just showing serial number
                choices.append(device_serial)
        
        # Use questionary to select device
        selected_choice = questionary.select(
            "Select a device:",
            choices=choices
        ).ask()
        
        if selected_choice:
            # Extract device serial from the choice (before the first space or parenthesis)
            device_serial = selected_choice.split()[0]
            return device_serial
        else:
            return None
            
    except Exception as e:
        import traceback
        print(f"Error listing devices: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return None


def select_installed_app(device_serial=None):
    """
    List installed apps and let user select one
    :param device_serial: serial number of target device
    :return: selected package name
    """
    try:
        # Create a temporary device instance to get installed apps
        print("Connecting to device...")
        device = Device(device_serial=device_serial)
        print("Getting installed apps...")
        installed_apps = device.adb.get_installed_apps()
        
        if not installed_apps:
            print("No installed apps found.")
            return None
            
        # Filter out system apps (optional - can be made configurable)
        user_apps = {}
        for package, path in installed_apps.items():
            # Skip system apps that are typically in /system/
            if not path.startswith('/system/'):
                user_apps[package] = path
        
        if not user_apps:
            print("No user apps found. Using all apps.")
            user_apps = installed_apps
            
        print(f"Found {len(user_apps)} apps")
        
        # Create choices for questionary
        choices = list(user_apps.keys())
        choices.sort()
        
        # Use questionary to select app
        selected_package = questionary.select(
            "Select an app to test:",
            choices=choices
        ).ask()
        
        return selected_package
        
    except Exception as e:
        import traceback
        print(f"Error listing apps: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return None


def parse_args():
    """
    parse command line input
    generate options including host name, port number
    """
    parser = argparse.ArgumentParser(description="Start DroidBot to test an Android app.",
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-d", action="store", dest="device_serial", required=False,
                        help="The serial number of target device (use `adb devices` to find)")
    parser.add_argument("-a", action="store", dest="apk_path", required=False,
                        help="The file path to target APK")
    parser.add_argument("-package_name", action="store", dest="package_name", required=False,
                        help="The package name of target app (for installed apps)")
    parser.add_argument("-o", action="store", dest="output_dir",
                        help="directory of output")
    # parser.add_argument("-env", action="store", dest="env_policy",
    #                     help="policy to set up environment. Supported policies:\n"
    #                          "none\tno environment will be set. App will run in default environment of device; \n"
    #                          "dummy\tadd some fake contacts, SMS log, call log; \n"
    #                          "static\tset environment based on static analysis result; \n"
    #                          "<file>\tget environment policy from a json file.\n")
    parser.add_argument("-policy", action="store", dest="input_policy", default=input_manager.DEFAULT_POLICY,
                        help='Policy to use for test input generation. '
                             'Default: %s.\nSupported policies:\n' % input_manager.DEFAULT_POLICY +
                             '  \"%s\" -- No event will be sent, user should interact manually with device; \n'
                             '  \"%s\" -- Use "adb shell monkey" to send events; \n'
                             '  \"%s\" -- Explore UI using a naive depth-first strategy;\n'
                             '  \"%s\" -- Explore UI using a greedy depth-first strategy;\n'
                             '  \"%s\" -- Explore UI using a naive breadth-first strategy;\n'
                             '  \"%s\" -- Explore UI using a greedy breadth-first strategy;\n'
                             %
                             (
                                 input_policy.PolicyType.NONE.value,
                                 input_policy.PolicyType.MONKEY.value,
                                 input_policy.PolicyType.NAIVE_DFS.value,
                                 input_policy.PolicyType.GREEDY_DFS.value,
                                 input_policy.PolicyType.NAIVE_BFS.value,
                                 input_policy.PolicyType.GREEDY_BFS.value,
                             ))

    # for distributed DroidBot
    parser.add_argument("-distributed", action="store", dest="distributed", choices=["master", "worker"],
                        help="Start DroidBot in distributed mode.")
    parser.add_argument("-master", action="store", dest="master",
                        help="DroidMaster's RPC address")
    parser.add_argument("-qemu_hda", action="store", dest="qemu_hda",
                        help="The QEMU's hda image")
    parser.add_argument("-qemu_no_graphic", action="store_true", dest="qemu_no_graphic",
                        help="Run QEMU with -nograpihc parameter")

    parser.add_argument("-script", action="store", dest="script_path",
                        help="Use a script to customize input for certain states.")
    parser.add_argument("-count", action="store", dest="count", default=input_manager.DEFAULT_EVENT_COUNT, type=int,
                        help="Number of events to generate in total. Default: %d" % input_manager.DEFAULT_EVENT_COUNT)
    parser.add_argument("-interval", action="store", dest="interval", default=input_manager.DEFAULT_EVENT_INTERVAL,
                        type=float,
                        help="Interval in seconds between each two events. Default: %.3f" % input_manager.DEFAULT_EVENT_INTERVAL)
    parser.add_argument("-timeout", action="store", dest="timeout", default=input_manager.DEFAULT_TIMEOUT, type=int,
                        help="Timeout in seconds, -1 means unlimited. Default: %d" % input_manager.DEFAULT_TIMEOUT)
    parser.add_argument("-cv", action="store_true", dest="cv_mode",
                        help="Use OpenCV (instead of UIAutomator) to identify UI components. CV mode requires opencv-python installed.")
    parser.add_argument("-debug", action="store_true", dest="debug_mode",
                        help="Run in debug mode (dump debug messages).")
    parser.add_argument("-random", action="store_true", dest="random_input",
                        help="Add randomness to input events.")
    parser.add_argument("-keep_app", action="store_true", dest="keep_app",
                        help="Keep the app on the device after testing.")
    parser.add_argument("-keep_env", action="store_true", dest="keep_env",
                        help="Keep the test environment (eg. minicap and accessibility service) after testing.")
    parser.add_argument("-use_method_profiling", action="store", dest="profiling_method",
                        help="Record method trace for each event. can be \"full\" or a sampling rate.")
    parser.add_argument("-grant_perm", action="store_true", dest="grant_perm",
                        help="Grant all permissions while installing. Useful for Android 6.0+.")
    parser.add_argument("-is_emulator", action="store_true", dest="is_emulator",
                        help="Declare the target device to be an emulator, which would be treated specially by DroidBot.")
    parser.add_argument("-accessibility_auto", action="store_true", dest="enable_accessibility_hard",
                        help="Enable the accessibility service automatically even though it might require device restart\n(can be useful for Android API level < 23).")
    parser.add_argument("-humanoid", action="store", dest="humanoid",
                        help="Connect to a Humanoid service (addr:port) for more human-like behaviors.")
    parser.add_argument("-ignore_ad", action="store_true", dest="ignore_ad",
                        help="Ignore Ad views by checking resource_id.")
    parser.add_argument("-replay_output", action="store", dest="replay_output",
                        help="The droidbot output directory being replayed.")
    options = parser.parse_args()
    # print options
    return options


def main():
    """
    the main function
    it starts a droidbot according to the arguments given in cmd line
    """
    opts = parse_args()
    import os
    
    # Handle device selection - should be done before app selection
    if not opts.device_serial:
        print("No device serial specified. Checking available devices...")
        selected_device = select_device()
        if not selected_device:
            print("No device selected. Exiting.")
            return
        opts.device_serial = selected_device
        print(f"Selected device: {opts.device_serial}")
    
    # Handle package_name parameter
    if opts.package_name:
        # Use the specified package name
        opts.apk_path = opts.package_name
        opts.keep_app = True
    # If no APK path and no package name provided
    elif not opts.apk_path:
        # Check if using manual policy - allow no app specification
        if opts.input_policy == "manual":
            print("Manual policy selected without specific app. Using system-wide manual mode...")
            opts.apk_path = "DUMMY_APP_FOR_MANUAL_MODE"  # Special marker
            opts.keep_app = True
        else:
            print("No APK path specified. Listing installed apps...")
            selected_package = select_installed_app(opts.device_serial)
            if not selected_package:
                print("No app selected. Exiting.")
                return
            # Use the selected package as the "apk_path" (DroidBot will handle it)
            opts.apk_path = selected_package
            opts.keep_app = True
    elif not os.path.exists(opts.apk_path):
        print("APK does not exist.")
        return
        
    if not opts.output_dir and opts.cv_mode:
        print("To run in CV mode, you need to specify an output dir (using -o option).")

    if opts.distributed:
        if opts.distributed == "master":
            start_mode = "master"
        else:
            start_mode = "worker"
    else:
        start_mode = "normal"

    if start_mode == "master":
        droidmaster = DroidMaster(
            app_path=opts.apk_path,
            is_emulator=opts.is_emulator,
            output_dir=opts.output_dir,
            # env_policy=opts.env_policy,
            env_policy=env_manager.EnvPolicyType.NONE.value,
            policy_name=opts.input_policy,
            random_input=opts.random_input,
            script_path=opts.script_path,
            event_interval=opts.interval,
            timeout=opts.timeout,
            event_count=opts.count,
            cv_mode=opts.cv_mode,
            debug_mode=opts.debug_mode,
            keep_app=opts.keep_app,
            keep_env=opts.keep_env,
            profiling_method=opts.profiling_method,
            grant_perm=opts.grant_perm,
            enable_accessibility_hard=opts.enable_accessibility_hard,
            qemu_hda=opts.qemu_hda,
            qemu_no_graphic=opts.qemu_no_graphic,
            humanoid=opts.humanoid,
            ignore_ad=opts.ignore_ad,
            replay_output=opts.replay_output)
        droidmaster.start()
    else:
        droidbot = DroidBot(
            app_path=opts.apk_path,
            device_serial=opts.device_serial,
            is_emulator=opts.is_emulator,
            output_dir=opts.output_dir,
            # env_policy=opts.env_policy,
            env_policy=env_manager.EnvPolicyType.NONE.value,
            policy_name=opts.input_policy,
            random_input=opts.random_input,
            script_path=opts.script_path,
            event_interval=opts.interval,
            timeout=opts.timeout,
            event_count=opts.count,
            cv_mode=opts.cv_mode,
            debug_mode=opts.debug_mode,
            keep_app=opts.keep_app,
            keep_env=opts.keep_env,
            profiling_method=opts.profiling_method,
            grant_perm=opts.grant_perm,
            enable_accessibility_hard=opts.enable_accessibility_hard,
            master=opts.master,
            humanoid=opts.humanoid,
            ignore_ad=opts.ignore_ad,
            replay_output=opts.replay_output)
        droidbot.start()
    return


if __name__ == "__main__":
    main()
