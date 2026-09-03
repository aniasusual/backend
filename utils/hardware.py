"""
Hardware detection utility for Lowkey.

Provides accurate, zero-overhead hardware inspection (OS, CPU chip, architecture,
total RAM, and Apple Silicon Unified Memory) to determine local LLM compatibility.
"""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Dict, Any


def detect_hardware() -> Dict[str, Any]:
    """
    Inspect the host machine's hardware capabilities.

    Returns:
        Dict with keys:
            - os: str ('Darwin', 'Linux', 'Windows')
            - arch: str ('arm64', 'x86_64', etc.)
            - chip_name: str (e.g. 'Apple M4', 'Intel Core i9-13900K')
            - total_ram_gb: float (e.g. 16.0)
            - is_apple_silicon: bool (True for Apple M-series chips)
            - cpu_cores: int
            - usable_ram_gb: float (estimated RAM budget for LLMs)
    """
    os_name = platform.system()
    arch = platform.machine()
    total_ram_gb = 0.0
    chip_name = platform.processor() or ""
    is_apple_silicon = False

    if os_name == "Darwin":
        try:
            mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip())
            total_ram_gb = round(mem_bytes / (1024**3), 1)
        except Exception:
            total_ram_gb = 8.0  # Fallback

        try:
            chip_name = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip()
        except Exception:
            pass

        is_apple_silicon = (arch == "arm64")
        if is_apple_silicon and (not chip_name or chip_name == "Apple"):
            try:
                model_id = subprocess.check_output(["sysctl", "-n", "hw.model"]).decode().strip()
                chip_name = f"Apple Silicon ({model_id})"
            except Exception:
                chip_name = "Apple Silicon"

    elif os_name == "Linux":
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        total_ram_gb = round(kb / (1024**2), 1)
                        break
        except Exception:
            total_ram_gb = 8.0

        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        chip_name = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

    elif os_name == "Windows":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_ram_gb = round(stat.ullTotalPhys / (1024**3), 1)
        except Exception:
            total_ram_gb = 8.0

    if not chip_name:
        chip_name = f"{arch.upper()} Processor"

    cpu_cores = os.cpu_count() or 4
    usable_ram_gb = max(1.0, round(total_ram_gb - 3.0, 1))

    return {
        "os": os_name,
        "arch": arch,
        "chip_name": chip_name,
        "total_ram_gb": total_ram_gb,
        "is_apple_silicon": is_apple_silicon,
        "cpu_cores": cpu_cores,
        "usable_ram_gb": usable_ram_gb,
    }
