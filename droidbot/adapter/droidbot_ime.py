# coding=utf-8

import logging
import time

from .adapter import Adapter

DROIDBOT_APP_PACKAGE = "io.github.ylimit.droidbotapp"
IME_SERVICE = DROIDBOT_APP_PACKAGE + "/.DroidBotIME"


class DroidBotImeException(Exception):
    """
    Exception in telnet connection
    """
    pass


class DroidBotIme(Adapter):
    """
    a connection with droidbot ime app.
    """
    def __init__(self, device=None):
        """
        initiate a emulator console via telnet
        :param device: instance of Device
        :return:
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        if device is None:
            from droidbot.device import Device
            device = Device()
        self.device = device
        self.connected = False
        self.original_ime = None  # 记录原始的默认输入法

    def set_up(self):
        """
        设置 DroidBot IME，包含安装验证和权限检查
        """
        device = self.device
        installed_apps = device.adb.get_installed_apps()
        
        if DROIDBOT_APP_PACKAGE in installed_apps:
            self.logger.info("DroidBot app is already installed")
            
            # 验证安装的完整性
            app_info = device.adb.shell(f"dumpsys package {DROIDBOT_APP_PACKAGE}")
            if "versionName" not in app_info:
                self.logger.warning("DroidBot app installation appears corrupted, reinstalling...")
                device.adb.shell(f"pm uninstall {DROIDBOT_APP_PACKAGE}")
                installed_apps.remove(DROIDBOT_APP_PACKAGE) if DROIDBOT_APP_PACKAGE in installed_apps else None
        
        if DROIDBOT_APP_PACKAGE not in installed_apps:
            self.logger.info("Installing DroidBot app...")
            try:
                from droidbot.resource_utils import get_droidbot_resource
                droidbot_app_path = get_droidbot_resource("droidbotApp.apk")
                
                # 验证 APK 文件存在
                import os
                if not os.path.exists(droidbot_app_path):
                    raise FileNotFoundError(f"DroidBot APK not found at: {droidbot_app_path}")
                
                self.logger.debug(f"Installing DroidBot app from: {droidbot_app_path}")
                install_cmd = ["install", "-r", droidbot_app_path]  # -r 允许重新安装
                result = self.device.adb.run_cmd(install_cmd)
                
                if "Success" in result or "INSTALL_SUCCEEDED" in result:
                    self.logger.info("DroidBot app installed successfully")
                    
                    # 验证安装
                    import time
                    time.sleep(2)  # 等待系统更新包列表
                    updated_apps = device.adb.get_installed_apps()
                    if DROIDBOT_APP_PACKAGE in updated_apps:
                        self.logger.info("Installation verified")
                    else:
                        raise Exception("Installation verification failed")
                else:
                    raise Exception(f"Installation failed: {result}")
                    
            except Exception as e:
                self.logger.error(f"Failed to install DroidBotApp: {str(e)}")
                self.logger.error(f"Error details: {type(e).__name__}")
                raise e
        
        # 检查 IME 权限
        self._check_ime_permissions()
    
    def _check_ime_permissions(self):
        """
        检查 DroidBot IME 应用的权限和服务状态
        """
        try:
            # 检查应用是否有输入法权限
            ime_list = self.device.adb.shell("ime list -a")
            if IME_SERVICE not in ime_list:
                self.logger.warning(f"DroidBot IME service {IME_SERVICE} not found in system IME list")
                self.logger.debug(f"Available IMEs: {ime_list}")
            else:
                self.logger.info("DroidBot IME service is available in system")
                
            # 检查应用权限
            app_perms = self.device.adb.shell(f"dumpsys package {DROIDBOT_APP_PACKAGE} | grep permission")
            self.logger.debug(f"App permissions: {app_perms}")
            
        except Exception as e:
            self.logger.warning(f"Failed to check IME permissions: {e}")
    
    def _save_original_ime(self):
        """
        保存当前的默认输入法，以便后续恢复
        """
        try:
            current_ime = self.device.adb.shell("settings get secure default_input_method").strip()
            if current_ime and current_ime != "null":
                self.original_ime = current_ime
                self.logger.info(f"Saved original IME: {self.original_ime}")
            else:
                self.logger.warning("No default IME found to save")
                # 如果没有默认输入法，尝试从已启用列表中找到一个
                self._find_fallback_ime()
        except Exception as e:
            self.logger.error(f"Failed to save original IME: {e}")
            self._find_fallback_ime()
    
    def _find_fallback_ime(self):
        """
        当无法获取当前默认输入法时，寻找一个合适的备用输入法
        """
        try:
            enabled_imes = self.device.adb.shell("ime list -e").strip()
            common_ime_patterns = [
                "com.google.android.inputmethod.latin",  # Gboard
                "com.android.inputmethod.latin",         # AOSP Latin
                "com.samsung.android.honeyboard",        # Samsung Keyboard
            ]
            
            ime_lines = [line.strip() for line in enabled_imes.split('\n') if line.strip()]
            
            for ime_line in ime_lines:
                if IME_SERVICE in ime_line:
                    continue
                    
                ime_service = ime_line.lstrip('* ').strip()
                if not ime_service:
                    continue
                
                # 优先选择常见的系统输入法
                for pattern in common_ime_patterns:
                    if pattern in ime_service:
                        self.original_ime = ime_service
                        self.logger.info(f"Selected fallback IME: {self.original_ime}")
                        return
                
                # 如果没有找到常见的，使用第一个可用的
                if not self.original_ime:
                    self.original_ime = ime_service
                    self.logger.info(f"Selected first available IME as fallback: {self.original_ime}")
                    return
                    
        except Exception as e:
            self.logger.error(f"Failed to find fallback IME: {e}")
    
    def _restore_default_ime(self):
        """
        恢复到记录的原始默认输入法
        """
        if not self.original_ime:
            self.logger.warning("No original IME recorded, cannot restore")
            return False
            
        try:
            self.logger.info(f"Restoring original IME: {self.original_ime}")
            
            # 检查原始输入法是否仍然可用
            enabled_imes = self.device.adb.shell("ime list -e").strip()
            if self.original_ime not in enabled_imes:
                self.logger.warning(f"Original IME {self.original_ime} is no longer enabled")
                # 尝试重新启用
                try:
                    enable_result = self.device.adb.shell(f"ime enable {self.original_ime}")
                    if "now enabled" not in enable_result and "already enabled" not in enable_result:
                        self.logger.error(f"Failed to re-enable original IME: {enable_result}")
                        return False
                except Exception as e:
                    self.logger.error(f"Failed to re-enable original IME: {e}")
                    return False
            
            # 设置为原始输入法
            result = self.device.adb.shell(f"ime set {self.original_ime}")
            self.logger.debug(f"Restore IME result: {result}")
            
            # 验证恢复是否成功
            import time
            time.sleep(1)
            current_ime = self.device.adb.shell("settings get secure default_input_method").strip()
            
            if self.original_ime in current_ime:
                self.logger.info("Original IME restored successfully")
                return True
            else:
                self.logger.warning(f"Failed to restore original IME. Current: {current_ime}, Expected: {self.original_ime}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error restoring original IME: {e}")
            return False

    def tear_down(self):
        self.device.uninstall_app(DROIDBOT_APP_PACKAGE)

    def connect(self):
        """
        连接 DroidBot IME，包含重试机制和详细的错误诊断
        """
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            self.logger.info(f"Attempting to connect DroidBotIME (attempt {attempt + 1}/{max_retries})")
            
            # 第一次尝试时记录当前的默认输入法
            if attempt == 0 and self.original_ime is None:
                self._save_original_ime()
            
            # 检查应用是否已安装
            installed_apps = self.device.adb.get_installed_apps()
            if DROIDBOT_APP_PACKAGE not in installed_apps:
                self.logger.warning(f"DroidBot app {DROIDBOT_APP_PACKAGE} is not installed")
                self.set_up()  # 尝试重新安装
                continue
                
            # 步骤1: 启用 IME 服务
            self.logger.debug(f"Enabling IME service: {IME_SERVICE}")
            r_enable = self.device.adb.shell(f"ime enable {IME_SERVICE}")
            self.logger.debug(f"Enable result: {r_enable}")
            
            if "now enabled" in r_enable or "already enabled" in r_enable:
                self.logger.info("IME service successfully enabled")
                
                # 短暂等待，确保系统识别 IME
                import time
                time.sleep(1)
                
                # 步骤2: 设置为当前 IME
                self.logger.debug(f"Setting IME as current: {IME_SERVICE}")
                r_set = self.device.adb.shell(f"ime set {IME_SERVICE}")
                self.logger.debug(f"Set result: {r_set}")
                
                if f"{IME_SERVICE} selected" in r_set or "Selected input method" in r_set:
                    self.logger.info("IME successfully set as current input method")
                    
                    # 步骤3: 验证 IME 状态
                    current_ime = self.device.adb.shell("settings get secure default_input_method")
                    self.logger.debug(f"Current default IME: {current_ime}")
                    
                    if IME_SERVICE in current_ime:
                        self.connected = True
                        self.logger.info("DroidBotIME connected successfully!")
                        return True
                    else:
                        self.logger.warning(f"IME not set as default. Current: {current_ime}")
                else:
                    self.logger.warning(f"Failed to set IME. Result: {r_set}")
            else:
                self.logger.warning(f"Failed to enable IME. Result: {r_enable}")
                
                # 检查 IME 是否在可用列表中
                available_imes = self.device.adb.shell("ime list -a")
                if IME_SERVICE in available_imes:
                    self.logger.info("IME is available in the system")
                else:
                    self.logger.error(f"IME {IME_SERVICE} is not available in system. Available IMEs:\n{available_imes}")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                self.logger.info(f"Retrying in {retry_delay} seconds...")
                import time
                time.sleep(retry_delay)
        
        self.logger.error(f"Failed to connect DroidBotIME after {max_retries} attempts!")
        return False

    def check_connectivity(self):
        """
        检查 droidbot IME 是否已连接，同时验证实际状态
        :return: True for connected
        """
        if not self.connected:
            return False
            
        # 验证 IME 是否仍然是当前输入法
        try:
            current_ime = self.device.adb.shell("settings get secure default_input_method").strip()
            if IME_SERVICE not in current_ime:
                self.logger.warning(f"IME no longer active. Current: {current_ime}")
                self.connected = False
                return False
            return True
        except Exception as e:
            self.logger.warning(f"Failed to verify IME status: {e}")
            return self.connected

    def disconnect(self):
        """
        断开 DroidBot IME 连接，恢复默认输入法
        """
        if not self.connected:
            self.logger.info("DroidBot IME is not connected")
            return
            
        try:
            # 首先禁用 DroidBot IME
            self.logger.info("Disabling DroidBot IME...")
            r_disable = self.device.adb.shell(f"ime disable {IME_SERVICE}")
            self.logger.debug(f"Disable result: {r_disable}")
            
            # 获取可用的输入法列表并选择合适的默认输入法
            self._restore_default_ime()
            
            if "now disabled" in r_disable or "is already disabled" in r_disable:
                self.connected = False
                self.logger.info("DroidBotIME disconnected successfully")
            else:
                self.logger.warning(f"Failed to disable DroidBotIME: {r_disable}")
                # 即使禁用失败，也标记为断开连接
                self.connected = False
                
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
        finally:
            self.connected = False

    def force_reset_ime(self):
        """
        强制重置 IME 状态，用于解决顽固的连接问题
        """
        self.logger.info("Force resetting IME...")
        
        try:
            # 先断开当前连接
            self.disconnect()
            
            # 清除设置缓存
            self.device.adb.shell("settings delete secure default_input_method")
            
            # 短暂等待
            import time
            time.sleep(2)
            
            # 如果有记录的原始输入法，先恢复它
            if self.original_ime:
                self.logger.info(f"Restoring original IME before reconnecting: {self.original_ime}")
                try:
                    self.device.adb.shell(f"ime set {self.original_ime}")
                    time.sleep(1)
                except Exception as e:
                    self.logger.warning(f"Failed to restore original IME during reset: {e}")
            
            # 重新连接
            return self.connect()
            
        except Exception as e:
            self.logger.error(f"Force reset failed: {e}")
            return False

    def input_text(self, text, mode=0):
        """
        Input text to target device
        :param text: text to input, can be unicode format
        :param mode: 0 - set text; 1 - append text.
        """
        if not self.check_connectivity():
            self.logger.warning("IME not connected, attempting to reconnect...")
            if not self.connect():
                self.logger.error("Failed to reconnect IME for text input")
                return False
                
        text_nospace = text.replace(' ', '--')
        input_cmd = 'am broadcast -a DROIDBOT_INPUT_TEXT --es text %s --ei mode %d' % (text_nospace, mode)
        result = self.device.adb.shell(str(input_cmd))
        self.logger.debug(f"Input text result: {result}")
        return True


if __name__ == "__main__":
    droidbot_ime_conn = DroidBotIme()
    droidbot_ime_conn.set_up()
    droidbot_ime_conn.connect()
    droidbot_ime_conn.input_text("hello world!", 0)
    droidbot_ime_conn.input_text("世界你好!", 1)
    time.sleep(2)
    droidbot_ime_conn.input_text("再见。Bye bye.", 0)
    droidbot_ime_conn.disconnect()
    droidbot_ime_conn.tear_down()
