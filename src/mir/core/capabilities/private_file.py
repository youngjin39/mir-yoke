"""Owner-only capability state files using POSIX modes or Windows DACLs."""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from ctypes import wintypes
from pathlib import Path

_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_SE_DACL_PRESENT = 0x0004
_SE_DACL_PROTECTED = 0x1000
_SE_FILE_OBJECT = 1


class _ACL(ctypes.Structure):
    _fields_ = [
        ("AclRevision", wintypes.BYTE), ("Sbz1", wintypes.BYTE),
        ("AclSize", wintypes.WORD), ("AceCount", wintypes.WORD), ("Sbz2", wintypes.WORD),
    ]


class _ACCESS_ALLOWED_ACE(ctypes.Structure):
    _fields_ = [
        ("AceType", wintypes.BYTE), ("AceFlags", wintypes.BYTE),
        ("AceSize", wintypes.WORD), ("Mask", wintypes.DWORD), ("SidStart", wintypes.DWORD),
    ]


def _check(success: object) -> None:
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())


class _WindowsSecurity:
    def __init__(self) -> None:
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        pointer = ctypes.POINTER
        void = ctypes.c_void_p
        for library, signatures in (
            (self.kernel, [
                ("GetCurrentProcess", wintypes.HANDLE, []),
                ("CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
                ("LocalFree", void, [void]),
            ]),
            (self.advapi, [
                ("OpenProcessToken", wintypes.BOOL,
                 [wintypes.HANDLE, wintypes.DWORD, pointer(wintypes.HANDLE)]),
                ("GetTokenInformation", wintypes.BOOL,
                 [wintypes.HANDLE, ctypes.c_int, void, wintypes.DWORD, pointer(wintypes.DWORD)]),
                ("ConvertSidToStringSidW", wintypes.BOOL, [void, pointer(wintypes.LPWSTR)]),
                ("ConvertStringSecurityDescriptorToSecurityDescriptorW", wintypes.BOOL,
                 [wintypes.LPCWSTR, wintypes.DWORD, pointer(void), pointer(wintypes.DWORD)]),
                ("GetSecurityDescriptorDacl", wintypes.BOOL,
                 [void, pointer(wintypes.BOOL), pointer(void), pointer(wintypes.BOOL)]),
                ("GetSecurityDescriptorControl", wintypes.BOOL,
                 [void, pointer(wintypes.WORD), pointer(wintypes.DWORD)]),
                ("SetNamedSecurityInfoW", wintypes.DWORD,
                 [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, void, void, void, void]),
                ("GetNamedSecurityInfoW", wintypes.DWORD,
                 [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, *([pointer(void)] * 5)]),
                ("GetAce", wintypes.BOOL, [void, wintypes.DWORD, pointer(void)]),
            ]),
        ):
            for name, result, arguments in signatures:
                function = getattr(library, name)
                function.argtypes = arguments
                function.restype = result

    def free(self, pointer: object) -> None:
        _check(not self.kernel.LocalFree(pointer))

    def sid_string(self, sid: object) -> str:
        value = wintypes.LPWSTR()
        _check(self.advapi.ConvertSidToStringSidW(sid, ctypes.byref(value)))
        try:
            return value.value
        finally:
            self.free(value)

    def current_user(self) -> str:
        token = wintypes.HANDLE()
        _check(self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x0008,
                                          ctypes.byref(token)))  # TOKEN_QUERY
        try:
            size = wintypes.DWORD()
            # TokenUser starts with a SID pointer. The first call sizes its buffer.
            result = self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if result or ctypes.get_last_error() != 122:  # ERROR_INSUFFICIENT_BUFFER
                raise ctypes.WinError(ctypes.get_last_error())
            buffer = ctypes.create_string_buffer(size.value)
            _check(self.advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)))
            return self.sid_string(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
        finally:
            _check(self.kernel.CloseHandle(token))

    def make_private(self, path: Path) -> None:
        descriptor = ctypes.c_void_p()
        # P disables inheritance; A/FA grants only this process user full file access.
        sddl = f"D:P(A;;FA;;;{self.current_user()})"
        _check(self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None,
        ))
        try:
            present, defaulted = wintypes.BOOL(), wintypes.BOOL()
            dacl = ctypes.c_void_p()
            _check(self.advapi.GetSecurityDescriptorDacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted),
            ))
            if not present or not dacl:
                raise OSError("private security descriptor has no DACL")
            error = self.advapi.SetNamedSecurityInfoW(
                str(path), _SE_FILE_OBJECT,
                _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
                None, None, dacl, None,
            )
            if error:
                raise ctypes.WinError(error)
        finally:
            self.free(descriptor)

    def is_private(self, path: Path) -> bool:
        descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
        error = self.advapi.GetNamedSecurityInfoW(
            str(path), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
            None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor),
        )
        if error:
            raise ctypes.WinError(error)
        try:
            control, revision = wintypes.WORD(), wintypes.DWORD()
            _check(self.advapi.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision),
            ))
            required = _SE_DACL_PRESENT | _SE_DACL_PROTECTED
            # A missing/NULL DACL grants everyone access; inheritance could widen access.
            if not dacl or control.value & required != required:
                return False
            allowed = {self.current_user(), "S-1-5-18", "S-1-5-32-544"}
            acl = ctypes.cast(dacl, ctypes.POINTER(_ACL)).contents
            for index in range(acl.AceCount):
                pointer = ctypes.c_void_p()
                _check(self.advapi.GetAce(dacl, index, ctypes.byref(pointer)))
                ace = ctypes.cast(pointer, ctypes.POINTER(_ACCESS_ALLOWED_ACE)).contents
                if ace.AceType != 0:  # ACCESS_ALLOWED_ACE_TYPE
                    return False
                sid = ctypes.byref(ace, _ACCESS_ALLOWED_ACE.SidStart.offset)
                if self.sid_string(sid) not in allowed:
                    return False
            return True
        finally:
            self.free(descriptor)


def make_private(path: Path) -> None:
    """Restrict a file to its current user; propagate permission/API failures."""
    if sys.platform == "win32":
        _WindowsSecurity().make_private(path)
    else:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def is_private(path: Path, metadata: os.stat_result) -> bool:
    """Check private permissions, failing closed when Windows cannot inspect them."""
    if sys.platform != "win32":
        return stat.S_IMODE(metadata.st_mode) == 0o600
    try:
        return _WindowsSecurity().is_private(path)
    except OSError:
        return False
