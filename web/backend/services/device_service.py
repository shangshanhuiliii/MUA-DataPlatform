import subprocess
from typing import List, Dict, Any, Optional
import logging

from ..schemas.device import Device

logger = logging.getLogger(__name__)

class DeviceService:
    """设备管理服务类"""

    @staticmethod
    async def get_connected_devices() -> List[Device]:
        """获取连接的Android设备列表"""
        try:
            result = subprocess.run(
                ['adb', 'devices'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                raise RuntimeError("Failed to get devices")

            devices = []
            lines = result.stdout.strip().split('\n')[1:]  # 跳过标题行

            for line in lines:
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2 and parts[1] == 'device':
                        # 获取设备详细信息
                        device_info = await DeviceService._get_device_info(parts[0])
                        devices.append(Device(
                            serial=parts[0],
                            status=parts[1],
                            **device_info
                        ))

            return devices
        except Exception as e:
            logger.error(f"Error getting devices: {e}")
            raise RuntimeError(f"Error getting devices: {str(e)}")

    @staticmethod
    async def _get_device_info(serial: str) -> Dict[str, Any]:
        """获取设备详细信息"""
        info = {}

        try:
            # 获取设备品牌
            result = await DeviceService._run_adb_command(
                serial, ['shell', 'getprop', 'ro.product.brand']
            )
            if result:
                info['brand'] = result.strip()

            # 获取设备型号
            result = await DeviceService._run_adb_command(
                serial, ['shell', 'getprop', 'ro.product.model']
            )
            if result:
                info['model'] = result.strip()

            # 获取Android版本
            result = await DeviceService._run_adb_command(
                serial, ['shell', 'getprop', 'ro.build.version.release']
            )
            if result:
                info['version'] = result.strip()

            # 获取API级别
            result = await DeviceService._run_adb_command(
                serial, ['shell', 'getprop', 'ro.build.version.sdk']
            )
            if result:
                try:
                    info['api_level'] = int(result.strip())
                except ValueError:
                    pass

        except Exception as e:
            logger.warning(f"Error getting device info for {serial}: {e}")

        return info

    @staticmethod
    async def _run_adb_command(serial: str, cmd: List[str], timeout: int = 10) -> Optional[str]:
        """运行ADB命令"""
        try:
            full_cmd = ['adb', '-s', serial] + cmd
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode == 0:
                return result.stdout
            return None
        except Exception:
            return None
