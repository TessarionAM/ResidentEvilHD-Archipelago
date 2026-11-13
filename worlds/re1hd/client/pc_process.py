"""
Read the memory of a running Windows program (Resident Evil HD Remaster's bhd.exe).

This is the Steam-version counterpart of dolphin_connection.py and offers the
same methods (connect / is_connected / read_bytes / disconnect), so the rest
of the project doesn't care which version of the game it is talking to.

It uses the Windows API directly through Python's built-in `ctypes` module,
so no extra packages are needed. It only READS memory, unless it is created
with writable=True (Milestone 6: delivering items into the item box). Writing
is opt-in so that every read-only tool stays unable to change the game.

How it works, in plain terms:
  1. Ask Windows for a list of running programs and find "bhd.exe".
  2. Ask Windows for permission to read that program's memory (OpenProcess).
  3. Read bytes at an address (ReadProcessMemory).
  4. (writable connections only) Write bytes at an address (WriteProcessMemory).
"""

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Optional

log = logging.getLogger("re_ap.pc")

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_PATH = 260


class ProcessError(Exception):
    """Raised when talking to the game process fails. Never swallowed silently."""


if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * MAX_PATH)]

    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
                    ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.c_void_p),
                    ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
                    ("szModule", wintypes.WCHAR * 256), ("szExePath", wintypes.WCHAR * MAX_PATH)]

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.VirtualProtectEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                          wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                        wintypes.DWORD, wintypes.DWORD]
    kernel32.VirtualAllocEx.restype = ctypes.c_void_p
    kernel32.FlushInstructionCache.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
    kernel32.IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_int)]

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        # 64-bit layout (our Python is 64-bit; this also works for a 32-bit game).
        _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                    ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                    ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
                    ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]

    kernel32.VirtualQueryEx.restype = ctypes.c_size_t
    kernel32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                        ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]

else:
    kernel32 = None

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_EXECUTE_READWRITE = 0x40
# Page protections we can safely read data from (read-only, read-write, write-copy, and exec variants).
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}

STILL_ACTIVE = 259


def _win_error(what: str) -> ProcessError:
    code = ctypes.get_last_error()
    return ProcessError(f"{what} failed (Windows error {code}: {ctypes.FormatError(code).strip()})")


def find_process_id(exe_name: str) -> Optional[int]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        raise _win_error("Listing processes")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == exe_name.lower():
                return entry.th32ProcessID
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
        return None
    finally:
        kernel32.CloseHandle(snap)


def find_module(pid: int, module_name: str):
    """Return (base address, size in bytes) of a module (e.g. bhd.exe) inside the process."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == INVALID_HANDLE_VALUE:
        raise _win_error("Listing modules")
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Module32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szModule.lower() == module_name.lower():
                return entry.modBaseAddr, entry.modBaseSize
            ok = kernel32.Module32NextW(snap, ctypes.byref(entry))
        raise ProcessError(f"Module {module_name} not found in process {pid}")
    finally:
        kernel32.CloseHandle(snap)


_SAID_NOT_RUNNING: dict = {}     # log "not running" once, not 10 times a second


class ProcessConnection:
    """Access to a running Windows process. Read-only unless writable=True."""

    def __init__(self, exe_name: str = "bhd.exe", writable: bool = False):
        if kernel32 is None:
            raise ProcessError("Reading the Steam version's memory only works on Windows.")
        self.exe_name = exe_name
        self.writable = writable
        self.pid: Optional[int] = None
        self.handle = None
        self.module_base: Optional[int] = None
        self.module_size: Optional[int] = None
        self.exe_path: Optional[str] = None

    def is_connected(self) -> bool:
        if not self.handle:
            return False
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(self.handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            log.info("%s has exited.", self.exe_name)
            self.disconnect()
            return False
        return True

    def connect(self) -> bool:
        if self.is_connected():
            return True
        pid = find_process_id(self.exe_name)
        if pid is None:
            if not _SAID_NOT_RUNNING.get(self.exe_name):
                log.info("%s is not running (yet).", self.exe_name)
                _SAID_NOT_RUNNING[self.exe_name] = True
            return False
        access = PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION
        if self.writable:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        handle = kernel32.OpenProcess(access, False, pid)
        if not handle:
            raise _win_error(f"Opening {self.exe_name} (pid {pid}) for {'writing' if self.writable else 'reading'}")
        self.pid, self.handle = pid, handle
        try:
            self.module_base, self.module_size = find_module(pid, self.exe_name)
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                raise _win_error("Getting the game's file path")
            self.exe_path = buf.value
        except ProcessError:
            self.disconnect()
            raise
        _SAID_NOT_RUNNING[self.exe_name] = False
        log.info("Attached to %s (pid %d, base 0x%08X).", self.exe_name, pid, self.module_base)
        return True

    def disconnect(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
        self.handle = None
        self.pid = None
        self.module_base = None

    def readable_regions(self, max_address: int = 0xFFFF0000):
        """Yield (start, size) for every committed, readable memory region of the game."""
        mbi = MEMORY_BASIC_INFORMATION()
        address = 0x10000
        while address < max_address:
            if not kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(address),
                                           ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            if (mbi.State == MEM_COMMIT and not (mbi.Protect & PAGE_GUARD)
                    and (mbi.Protect & 0xFF) in READABLE):
                yield base, size
            address = base + size
            if size == 0:
                break

    def read_bytes(self, address: int, size: int) -> bytes:
        if not self.is_connected():
            raise ProcessError("Not connected to the game.")
        buf = (ctypes.c_ubyte * size)()
        got = ctypes.c_size_t(0)
        if not kernel32.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got)):
            raise _win_error(f"Reading 0x{address:08X} (+{size})")
        if got.value != size:
            raise ProcessError(f"Short read at 0x{address:08X}: wanted {size}, got {got.value}")
        # Reads are NOT logged (2026-11-11): the client reads many times a second, which made
        # 25-70 MB log files, and hex-dumping big reads cost a lot of memory. Writes are logged.
        return bytes(buf)

    def write_bytes(self, address: int, data: bytes) -> None:
        """Write data at address. Only allowed on a writable connection. Every write is logged."""
        if not self.writable:
            raise ProcessError("This connection is read-only; writing is not allowed.")
        if not self.is_connected():
            raise ProcessError("Not connected to the game.")
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        done = ctypes.c_size_t(0)
        if not kernel32.WriteProcessMemory(self.handle, ctypes.c_void_p(address), buf, len(data), ctypes.byref(done)):
            raise _win_error(f"Writing 0x{address:08X} (+{len(data)})")
        if done.value != len(data):
            raise ProcessError(f"Short write at 0x{address:08X}: wanted {len(data)}, wrote {done.value}")
        log.info("WROTE 0x%08X (+%d) <- %s", address, len(data), data.hex(" "))

    def write_code(self, address: int, data: bytes) -> None:
        """Write over the game's CODE (read-only pages): unprotect, write, restore, flush.
        Used only for small verified patches (door skip). Every write is logged."""
        if not self.writable:
            raise ProcessError("This connection is read-only; writing is not allowed.")
        old = wintypes.DWORD(0)
        if not kernel32.VirtualProtectEx(self.handle, ctypes.c_void_p(address), len(data),
                                         PAGE_EXECUTE_READWRITE, ctypes.byref(old)):
            raise _win_error(f"Unprotecting 0x{address:08X}")
        try:
            self.write_bytes(address, data)
        finally:
            kernel32.VirtualProtectEx(self.handle, ctypes.c_void_p(address), len(data),
                                      old.value, ctypes.byref(wintypes.DWORD(0)))
            kernel32.FlushInstructionCache(self.handle, ctypes.c_void_p(address), len(data))

    def alloc_code(self, size: int) -> int:
        """Reserve a small executable page inside the game (for the autosave hook)."""
        if not self.writable:
            raise ProcessError("This connection is read-only; writing is not allowed.")
        addr = kernel32.VirtualAllocEx(self.handle, None, size, 0x3000, PAGE_EXECUTE_READWRITE)
        if not addr:
            raise _win_error("Reserving memory in the game")
        log.info("Reserved %d bytes of code memory at 0x%08X.", size, addr)
        return addr

    def modules(self):
        """(name, full path) of every DLL loaded in the game (to check what mods are active)."""
        out = []
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, self.pid)
        if snap == INVALID_HANDLE_VALUE:
            raise _win_error("Listing modules")
        try:
            entry = MODULEENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            ok = kernel32.Module32FirstW(snap, ctypes.byref(entry))
            while ok:
                out.append((entry.szModule, entry.szExePath))
                ok = kernel32.Module32NextW(snap, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snap)
        return out
