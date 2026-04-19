"""
Resource utilities for DroidBot
This module provides modern resource path resolution to replace deprecated pkg_resources
"""
import os
from typing import Union
from pathlib import Path


def get_resource_path(package: str, resource: str) -> str:
    """
    Get the path to a resource file using modern importlib.resources.
    
    Falls back to pkg_resources for compatibility with older Python versions.
    
    Args:
        package: Package name (e.g., "droidbot.resources")
        resource: Resource filename (e.g., "droidbotApp.apk")
        
    Returns:
        Absolute path to the resource file
        
    Raises:
        FileNotFoundError: If the resource cannot be found
        ImportError: If no resource loading mechanism is available
    """
    try:
        # Use modern importlib.resources for Python 3.9+
        from importlib import resources
        with resources.path(package, resource) as resource_path:
            return str(resource_path)
    except (ImportError, AttributeError):
        # Fallback for Python < 3.9 or if importlib.resources is not available
        try:
            import importlib_resources as resources
            with resources.path(package, resource) as resource_path:
                return str(resource_path)
        except ImportError:
            # Final fallback to pkg_resources (deprecated but still works)
            import pkg_resources
            return pkg_resources.resource_filename(package.replace('.', '/'), resource)


def get_droidbot_resource(resource_name: str) -> str:
    """
    Convenience function to get a DroidBot resource path.
    
    Args:
        resource_name: Name of the resource file in droidbot/resources/
        
    Returns:
        Absolute path to the resource file
    """
    return get_resource_path("droidbot.resources", resource_name)


def get_droidbot_resource_dir(dir_name: str) -> str:
    """
    Get the path to a resource directory.
    
    Args:
        dir_name: Name of the directory in droidbot/resources/
        
    Returns:
        Absolute path to the resource directory
    """
    # For directories, we need to get the parent resources directory
    # and then construct the path to the subdirectory
    try:
        # Use modern importlib.resources for Python 3.9+
        from importlib import resources
        with resources.path("droidbot", "resources") as resources_path:
            return str(resources_path / dir_name)
    except (ImportError, AttributeError):
        # Fallback for Python < 3.9 or if importlib.resources is not available
        try:
            import importlib_resources as resources
            with resources.path("droidbot", "resources") as resources_path:
                return str(resources_path / dir_name)
        except ImportError:
            # Final fallback to pkg_resources (deprecated but still works)
            import pkg_resources
            return pkg_resources.resource_filename("droidbot", f"resources/{dir_name}")