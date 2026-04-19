"""
CloudDeviceService - 火山引擎云手机 ADB 管理服务
封装火山引擎 ACEP API 调用，管理云手机 ADB 连接
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class CloudDeviceService:
    """云手机设备服务 - 管理火山引擎云手机的 ADB 连接"""

    # ADB 过期时间阈值（小时）- 少于此时间则重新开启
    ADB_EXPIRE_THRESHOLD_HOURS = 6

    def __init__(self):
        self.ak = os.environ.get("VOLC_ACCESSKEY")
        self.sk = os.environ.get("VOLC_SECRETKEY")
        self.region = os.environ.get("VOLC_REGION", "cn-north-1")
        self._api_client = None

    def _get_api_client(self):
        """获取火山引擎 API 客户端（延迟初始化）"""
        if self._api_client is None:
            # 检查凭证是否配置
            if not self.ak or not self.sk:
                raise RuntimeError(
                    "Volcengine credentials not configured. "
                    "Please set VOLC_ACCESSKEY and VOLC_SECRETKEY environment variables."
                )
            try:
                import volcenginesdkcore
                configuration = volcenginesdkcore.Configuration()
                configuration.ak = self.ak
                configuration.sk = self.sk
                configuration.region = self.region
                self._api_client = volcenginesdkcore.UniversalApi(
                    volcenginesdkcore.ApiClient(configuration)
                )
            except ImportError:
                logger.error("volcenginesdkcore not installed")
                raise RuntimeError("volcenginesdkcore SDK not installed")
        return self._api_client

    async def get_pod_detail(self, product_id: str, pod_id: str) -> dict:
        """
        获取 Pod 详情
        返回包含 AdbStatus, Adb, AdbExpireTime 等字段
        """
        try:
            import volcenginesdkcore
            api = self._get_api_client()

            body = volcenginesdkcore.Flatten({
                "ProductId": product_id,
                "PodId": pod_id,
            }).flat()

            resp = await asyncio.to_thread(
                api.do_call,
                volcenginesdkcore.UniversalInfo(
                    method="POST",
                    action="DetailPod",
                    service="ACEP",
                    version="2023-10-30",
                    content_type="application/json"
                ),
                body
            )

            logger.info(f"Pod detail for {pod_id}: AdbStatus={resp.get('AdbStatus')}")
            return resp or {}

        except Exception as e:
            logger.error(f"Failed to get pod detail: {e}")
            raise RuntimeError(f"Failed to get pod detail: {e}")

    async def enable_adb(self, product_id: str, pod_id: str) -> bool:
        """开启 ADB"""
        try:
            import volcenginesdkcore
            api = self._get_api_client()

            body = volcenginesdkcore.Flatten({
                "ProductId": product_id,
                "PodId": pod_id,
                "Enable": True,
            }).flat()

            await asyncio.to_thread(
                api.do_call,
                volcenginesdkcore.UniversalInfo(
                    method="POST",
                    action="PodAdb",
                    service="ACEP",
                    version="2023-10-30",
                    content_type="application/json"
                ),
                body
            )

            logger.info(f"ADB enabled for pod {pod_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to enable ADB: {e}")
            raise RuntimeError(f"Failed to enable ADB: {e}")

    async def disable_adb(self, product_id: str, pod_id: str) -> bool:
        """关闭 ADB"""
        try:
            import volcenginesdkcore
            api = self._get_api_client()

            body = volcenginesdkcore.Flatten({
                "ProductId": product_id,
                "PodId": pod_id,
                "Enable": False,
            }).flat()

            await asyncio.to_thread(
                api.do_call,
                volcenginesdkcore.UniversalInfo(
                    method="POST",
                    action="PodAdb",
                    service="ACEP",
                    version="2023-10-30",
                    content_type="application/json"
                ),
                body
            )

            logger.info(f"ADB disabled for pod {pod_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to disable ADB: {e}")
            raise RuntimeError(f"Failed to disable ADB: {e}")

    async def ensure_adb_connection(
        self, product_id: str, pod_id: str, force_reconnect: bool = False
    ) -> Tuple[str, Optional[datetime]]:
        """
        确保 ADB 可用并返回连接地址

        逻辑：
        1. 获取 Pod 详情
        2. 如果 ADB 未开启：开启 ADB
        3. 如果 ADB 已开启但快过期（<6h）：关闭后重新开启
        4. 如果 ADB 已开启且未过期：直接使用

        Returns:
            Tuple[str, Optional[datetime]]: (ADB 地址, 过期时间)
        """
        # 获取 Pod 详情
        detail = await self.get_pod_detail(product_id, pod_id)

        adb_status = detail.get("AdbStatus", 0)
        adb_address = detail.get("Adb", "")
        adb_expire_time_str = detail.get("AdbExpireTime", "")

        # 解析过期时间
        adb_expire_time = None
        if adb_expire_time_str:
            try:
                if isinstance(adb_expire_time_str, int):
                    # Unix 时间戳
                    adb_expire_time = datetime.fromtimestamp(adb_expire_time_str)
                else:
                    # ISO 格式字符串
                    adb_expire_time = datetime.fromisoformat(
                        adb_expire_time_str.replace("Z", "+00:00")
                    )
            except (ValueError, OSError):
                logger.warning(f"Failed to parse AdbExpireTime: {adb_expire_time_str}")

        need_restart = False

        if adb_status != 1:
            # ADB 未开启，需要开启
            logger.info(f"ADB not enabled for pod {pod_id}, enabling...")
            need_restart = True
        elif force_reconnect:
            # 强制重连
            logger.info(f"Force reconnect requested for pod {pod_id}")
            need_restart = True
        elif adb_expire_time:
            # 检查过期时间
            time_until_expire = adb_expire_time - datetime.now(adb_expire_time.tzinfo)
            hours_until_expire = time_until_expire.total_seconds() / 3600

            if hours_until_expire < self.ADB_EXPIRE_THRESHOLD_HOURS:
                logger.info(
                    f"ADB for pod {pod_id} expires in {hours_until_expire:.1f}h, "
                    f"less than threshold {self.ADB_EXPIRE_THRESHOLD_HOURS}h, restarting..."
                )
                need_restart = True
            else:
                logger.info(
                    f"ADB for pod {pod_id} expires in {hours_until_expire:.1f}h, using existing"
                )

        if need_restart:
            # 如果 ADB 已开启，先关闭
            if adb_status == 1:
                await self.disable_adb(product_id, pod_id)
                await asyncio.sleep(1)  # 等待关闭完成

            # 开启 ADB
            await self.enable_adb(product_id, pod_id)
            await asyncio.sleep(2)  # 等待开启完成

            # 重新获取详情以获取新的 ADB 地址
            detail = await self.get_pod_detail(product_id, pod_id)
            adb_address = detail.get("Adb", "")
            adb_expire_time_str = detail.get("AdbExpireTime", "")

            if adb_expire_time_str:
                try:
                    if isinstance(adb_expire_time_str, int):
                        adb_expire_time = datetime.fromtimestamp(adb_expire_time_str)
                    else:
                        adb_expire_time = datetime.fromisoformat(
                            adb_expire_time_str.replace("Z", "+00:00")
                        )
                except (ValueError, OSError):
                    pass

        if not adb_address:
            raise RuntimeError(f"Failed to get ADB address for pod {pod_id}")

        return adb_address, adb_expire_time

    async def adb_connect(self, adb_address: str) -> bool:
        """执行 adb connect 命令"""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["adb", "connect", adb_address],
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout + result.stderr
            logger.info(f"adb connect {adb_address}: {output.strip()}")

            # 检查连接结果
            if "connected" in output.lower() or "already connected" in output.lower():
                return True

            logger.warning(f"adb connect may have failed: {output}")
            return True  # 即使输出不明确，也尝试继续

        except Exception as e:
            logger.error(f"Failed to run adb connect: {e}")
            raise RuntimeError(f"Failed to connect via ADB: {e}")

    async def check_device_locked(self, product_id: str, pod_id: str) -> bool:
        """
        检查设备是否被锁定
        1. 查询云端 ADB 状态，获取 ADB 地址
        2. 如果 ADB 未开启，设备不可能被锁定
        3. 如果 ADB 已开启，检查 unified device session 是否仍占用该地址
        """
        from backend.session_config import is_device_locked

        try:
            detail = await self.get_pod_detail(product_id, pod_id)
            adb_status = detail.get("AdbStatus", 0)
            adb_address = detail.get("Adb", "")

            # ADB 未开启，设备不可能被锁定
            if adb_status != 1 or not adb_address:
                return False

            return await is_device_locked(adb_address)

        except Exception as e:
            logger.warning(f"Failed to check device lock status: {e}")
            return False


# 全局服务实例
cloud_device_service = CloudDeviceService()
