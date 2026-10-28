"""Bounded read-only stdio tools, Python 3.11+, with no environment inputs."""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

try:
    import tomllib
except ImportError:
    tomllib = None

VERSION = "0.13.46"
MODERN = "2026-07-28"
LEGACY = "2025-11-25"
VERSIONS = [MODERN, LEGACY]
FRAME_LIMIT = 65536
FILE_LIMIT = 1048576
READ_LIMIT = 4194304
FILE_COUNT = 256
OUTPUT_LIMIT = 16384
STRING_LIMIT = 4096
# Git for Windows 2.56 moved the real binary from mingw64 to ucrt64; no PATH search, no wrapper.
WINDOWS_GITS = (
    r"C:\Program Files\Git\ucrt64\bin\git.exe",
    r"C:\Program Files\Git\mingw64\bin\git.exe",
)


def windows_git(exists=os.path.isfile):
    return next((path for path in WINDOWS_GITS if exists(path)), WINDOWS_GITS[0])


GIT_PREFIX = (
    windows_git() if sys.platform == "win32" else "/usr/bin/git",
    "--no-optional-locks", "--literal-pathspecs",
    "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
    "-c", "core.hooksPath=/dev/null", "-c", "core.attributesFile=/dev/null",
    "-c", "submodule.recurse=false",
)
GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
GIT_OUTPUT_LIMIT = 65536
# Seconds of the 10 s call budget Git may not use, so the call answers before the alarm.
GIT_RESERVE = 1
PACKAGE = Path(__file__).resolve().parent
PROTECTED = (
    ".env*",
    "*.db*",
    "*.sqlite*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    "credentials*",
    "token.json",
    "tokens.json",
    "id_rsa*",
    "id_ed25519*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
)
PROTECTED_DIRS = {"secrets", ".ssh", ".aws", ".gnupg"}
ERRORS = [
    "E_SCHEMA",
    "E_PATH",
    "E_CLOUD_SYNC",
    "E_PROTECTED",
    "E_LIMIT",
    "E_FORMAT",
    "E_VERSION",
    "E_IO",
    "E_GIT",
    "E_TIMEOUT",
    "E_CURSOR",
]


class Refusal(Exception):
    """Only a stable code and explicit unknowns may cross the tool boundary."""

    def __init__(self, code, unknowns=None):
        self.code = code
        self.unknowns = unknowns
        super().__init__(code)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_structure(value, depth=0):
    if depth > 32:
        raise Refusal("E_LIMIT")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > STRING_LIMIT:
            raise Refusal("E_LIMIT")
    elif isinstance(value, dict):
        for key, item in value.items():
            bounded_structure(key, depth + 1)
            bounded_structure(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            bounded_structure(item, depth + 1)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal("E_FORMAT")
        result[key] = value
    return result


def parse_json(raw):
    # Bound nesting before the decoder allocates a deeply nested object.
    level, quoted, escaped = 0, False, False
    for char in raw.decode("utf-8"):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            level += 1
            if level > 32:
                raise Refusal("E_LIMIT")
        elif char in "]}":
            level -= 1
    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(Refusal("E_FORMAT")),
        )
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal("E_FORMAT") from None
    bounded_structure(value)
    return value


if sys.platform == "win32":
    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    )
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.GetFinalPathNameByHandleW.argtypes = (
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
    )
    kernel32.GetFinalPathNameByHandleW.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int


def windows_components(parts, pattern=False):
    """Reject Win32 device, stream and normalization spellings without native calls."""
    for part in parts:
        device = part.split(".", 1)[0].upper()
        if (
            any(char in part for char in (':"<>|' if pattern else ':*?"<>|'))
            or part.endswith((".", " "))
            or device in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
            or re.fullmatch(r"(?:COM|LPT)[0-9¹²³]", device)
        ):
            raise Refusal("E_PATH")


def windows_root(value):
    """Admit only absolute local drive roots, including after resolution."""
    path = PureWindowsPath(value)
    if (
        not re.fullmatch(r"[a-zA-Z]:", path.drive)
        or path.root != "\\"
        or ".." in path.parts
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise Refusal("E_PATH")
    windows_components(path.parts[1:])


def windows_open(path, directory=False, protected=None):
    """Open without following reparses and prove the path of this exact handle."""
    native = kernel32.CreateFileW(
        str(path), 0x80000000, 0x1 | 0x2, None, 3, 0x00200000 | 0x02000000, None
    )  # GENERIC_READ; SHARE_READ|WRITE; OPEN_EXISTING; OPEN_REPARSE_POINT|BACKUP_SEMANTICS
    if native == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    handle = None
    try:
        opened = native
        handle = msvcrt.open_osfhandle(native, os.O_RDONLY | os.O_NOINHERIT)
        native = None  # The CRT descriptor now owns the native handle.
        info = os.fstat(handle)
        if (
            getattr(info, "st_file_attributes", 0) & 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
            or (directory and not stat.S_ISDIR(info.st_mode))
            or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
        ):
            raise Refusal("E_PATH")
        buffer = ctypes.create_unicode_buffer(32768)
        # FILE_NAME_NORMALIZED | VOLUME_NAME_DOS are both zero.
        length = kernel32.GetFinalPathNameByHandleW(opened, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise Refusal("E_PATH")
        final = buffer.value
        if not final.startswith("\\\\?\\"):
            raise Refusal("E_PATH")
        final = final[4:]
        windows_root(final)  # Also refuses mapped drives whose final path is UNC.
        if protected is not None:
            protected(Path(final))
        if os.path.normcase(final) != os.path.normcase(str(path)):
            raise Refusal("E_PATH")
        result = handle
        handle = None
        return result
    finally:
        if handle is not None:
            os.close(handle)
        if native is not None:
            kernel32.CloseHandle(native)


def windows_walk(root, parts, protected=None):
    """Keep all ancestors open without delete sharing until the caller closes them."""
    handles = []
    try:
        path = root
        handles.append(windows_open(path, True, protected))
        for index, part in enumerate(parts):
            path = path / part
            handles.append(windows_open(path, index < len(parts) - 1, protected))
        return handles
    except BaseException:
        for handle in reversed(handles):
            os.close(handle)
        raise


def relative_path(value, pattern=False):
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 4096
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or "\\" in value
        or value.startswith("-")
        or PureWindowsPath(value).drive
        or PurePosixPath(value).is_absolute()
        or ".." in PurePosixPath(value).parts
    ):
        raise Refusal("E_PATH")
    parts = PurePosixPath(value).parts
    if not parts or parts == (".",):
        raise Refusal("E_PATH")
    if sys.platform == "win32":
        windows_components(parts, pattern)
    return "/".join(parts)


def cloud_sync_reason(path):
    """Classify a resolved root using cloud attributes or macOS path components."""
    cloud_attributes = 0x80000 | 0x100000 | 0x40000 | 0x400000 | 0x1000
    for component in (path, *path.parents):
        info = os.stat(component, follow_symlinks=False)
        if getattr(info, "st_file_attributes", 0) & cloud_attributes:
            return "Windows cloud files"
    parts = tuple(part.lower() for part in path.parts)
    if len(parts) >= 5 and parts[:2] == ("/", "users") and parts[3] == "library":
        if parts[4] == "cloudstorage":
            return "macOS CloudStorage"
        if parts[4] == "mobile documents":
            return "iCloud Drive"
    return None


class Guard:
    """Every target access uses pinned directory descriptors and bounded reads."""

    def __init__(self, root):
        self.fd = None
        self.windows_ancestors = {}
        self.deadline = time.monotonic() + 10
        self.total = 0
        self.files = 0
        self.accessed = set()
        self.sources = {}
        self.source_digests = {}
        self.patterns = []
        self.profile_stamp = None
        self.profile_pinned = False
        self.profile_protections = "unavailable" if tomllib is None else "available"
        if (
            not isinstance(root, str)
            or len(root.encode("utf-8")) > 4096
            or (sys.platform != "win32" and not Path(root).is_absolute())
            or ".." in Path(root).parts
        ):
            raise Refusal("E_PATH")
        if sys.platform == "win32":
            windows_root(root)
        try:
            self.protected(root.replace("\\", "/") if sys.platform == "win32" else root)
            self.root = Path(root).resolve(strict=True)
            if sys.platform == "win32":
                windows_root(str(self.root))
            reason = cloud_sync_reason(self.root)
            if reason is not None:
                raise Refusal("E_CLOUD_SYNC", [
                    "target_root is inside a cloud-synced folder (" + reason + "); "
                    "Mir does not run there. Move the repository to a local folder."
                ])
            self.protected(self.root.as_posix())
            before = self.root.stat()
            if sys.platform == "win32":
                self.fd = windows_open(self.root, True, self._windows_protected)
            else:
                self.fd = os.open(str(self.root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            after = os.fstat(self.fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise Refusal("E_PATH")
            self.identity = (after.st_dev, after.st_ino)
            if tomllib is not None:
                self.profile_stamp = self._profile_stamp()
            if tomllib is not None and self.exists(".mir/repo-profile.toml"):
                raw = self.read(".mir/repo-profile.toml")
                try:
                    profile = tomllib.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeError):
                    raise Refusal("E_FORMAT") from None
                bounded_structure(profile)
                sections = (
                    (profile, ("protected_paths", "secret_paths")),
                    (profile.get("paths", {}), ("protected_paths", "secret_paths")),
                    (profile.get("boundaries", {}), ("secrets",)),
                    (profile.get("safety", {}), ("protected_paths", "secret_paths")),
                )
                for section, keys in sections:
                    if not isinstance(section, dict):
                        raise Refusal("E_FORMAT")
                    for key in keys:
                        patterns = section.get(key, [])
                        if not isinstance(patterns, list) or len(patterns) > 256:
                            raise Refusal("E_FORMAT")
                        for pattern in patterns:
                            try:
                                self.patterns.append(relative_path(pattern, pattern=True).lower())
                            except Refusal:
                                raise Refusal("E_FORMAT") from None
            if tomllib is not None:
                if self._profile_stamp() != self.profile_stamp:
                    raise Refusal("E_PATH")
                self.profile_pinned = True
        except BaseException:
            self.close()
            raise

    def close(self):
        for handle in list(self.windows_ancestors):
            self._close(handle)
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _close(self, handle):
        try:
            os.close(handle)
        finally:
            for ancestor in reversed(self.windows_ancestors.pop(handle, [])):
                os.close(ancestor)

    def _windows_protected(self, final):
        self.protected(final.as_posix())
        try:
            relative = final.relative_to(self.root).as_posix()
        except ValueError:
            raise Refusal("E_PATH") from None
        self.protected(relative)

    def tick(self):
        if time.monotonic() >= self.deadline:
            raise Refusal("E_TIMEOUT")
        try:
            current = self.root.stat()
            if (current.st_dev, current.st_ino) != self.identity:
                raise Refusal("E_PATH")
        except OSError:
            raise Refusal("E_PATH") from None
        if self.profile_pinned and self._profile_stamp() != self.profile_stamp:
            raise Refusal("E_PATH")

    def _profile_stamp(self):
        if sys.platform == "win32":
            handles = []
            try:
                handles = windows_walk(self.root, (".mir", "repo-profile.toml"))
                info = os.fstat(handles[-1])
                if not stat.S_ISREG(info.st_mode):
                    raise Refusal("E_PATH")
                return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            except FileNotFoundError:
                return "missing"
            except OSError:
                raise Refusal("E_PATH") from None
            finally:
                for handle in reversed(handles):
                    os.close(handle)
        directory = None
        handle = None
        try:
            directory = os.open(
                ".mir", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd
            )
            handle = os.open(
                "repo-profile.toml", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode):
                raise Refusal("E_PATH")
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        except FileNotFoundError:
            return "missing"
        except OSError:
            raise Refusal("E_PATH") from None
        finally:
            if handle is not None:
                os.close(handle)
            if directory is not None:
                os.close(directory)

    def protected(self, relative):
        parts = PurePosixPath(relative.lower()).parts
        for part in parts:
            if part in PROTECTED_DIRS or any(fnmatch.fnmatchcase(part, p) for p in PROTECTED):
                raise Refusal("E_PROTECTED")
        folded = "/".join(parts)
        for pattern in self.patterns:
            prefix = pattern[:-3] if pattern.endswith("/**") else pattern.rstrip("/")
            if (
                fnmatch.fnmatchcase(folded, pattern)
                or folded == prefix
                or folded.startswith(prefix + "/")
            ):
                raise Refusal("E_PROTECTED")

    def _relative(self, raw):
        if isinstance(raw, Path) and raw.is_absolute():
            try:
                raw = raw.relative_to(self.root).as_posix()
            except ValueError:
                raise Refusal("E_PATH") from None
        return relative_path(raw)

    def _open(self, raw, allow_missing=False):
        self.tick()
        relative = self._relative(raw)
        self.protected(relative)
        try:
            resolved = (self.root / relative).resolve()
            resolved_relative = resolved.relative_to(self.root).as_posix()
        except (OSError, ValueError, RuntimeError):
            raise Refusal("E_PATH") from None
        self.protected(resolved_relative)
        if sys.platform == "win32":
            return self._windows_open(relative, allow_missing)
        # O_NOFOLLOW on every component also refuses replacement by an internal symlink.
        directory = os.dup(self.fd)
        try:
            parts = PurePosixPath(relative).parts
            for index, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if index < len(parts) - 1:
                    flags |= os.O_DIRECTORY
                try:
                    child = os.open(part, flags, dir_fd=directory)
                except FileNotFoundError:
                    self.sources[relative] = "missing"
                    if allow_missing:
                        return None
                    raise Refusal("E_IO") from None
                except OSError:
                    raise Refusal("E_PATH") from None
                os.close(directory)
                directory = child
            info = os.fstat(directory)
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise Refusal("E_PATH")
            if stat.S_ISREG(info.st_mode):
                self.accessed.add(relative)
                if len(self.accessed) > FILE_COUNT:
                    raise Refusal("E_LIMIT")
            self.sources[relative] = [info.st_dev, info.st_ino, info.st_size,
                                      info.st_mtime_ns, info.st_ctime_ns]
            result = directory
            directory = None
            return result
        finally:
            if directory is not None:
                os.close(directory)

    def _windows_open(self, relative, allow_missing):
        handles = []
        try:
            try:
                handles = windows_walk(
                    self.root, PurePosixPath(relative).parts, self._windows_protected
                )
            except FileNotFoundError:
                self.sources[relative] = "missing"
                if allow_missing:
                    return None
                raise Refusal("E_IO") from None
            except OSError:
                raise Refusal("E_PATH") from None
            info = os.fstat(handles[-1])
            if stat.S_ISREG(info.st_mode):
                self.accessed.add(relative)
                if len(self.accessed) > FILE_COUNT:
                    raise Refusal("E_LIMIT")
            self.sources[relative] = [info.st_dev, info.st_ino, info.st_size,
                                      info.st_mtime_ns, info.st_ctime_ns]
            result = handles[-1]
            self.windows_ancestors[result] = handles[:-1]
            handles = []
            return result
        finally:
            for handle in reversed(handles):
                os.close(handle)

    def path(self, relative, allow_missing=False):
        normalized = self._relative(relative)
        handle = self._open(normalized, allow_missing)
        if handle is not None:
            self._close(handle)
        return self.root / normalized

    def exists(self, relative):
        handle = self._open(relative, True)
        if handle is None:
            return False
        self._close(handle)
        return True

    def read(self, relative):
        normalized = self._relative(relative)
        handle = self._open(normalized)
        try:
            before = os.fstat(handle)
            if not stat.S_ISREG(before.st_mode):
                raise Refusal("E_PATH")
            self.files += 1
            if self.files > FILE_COUNT or before.st_size > FILE_LIMIT:
                raise Refusal("E_LIMIT")
            chunks = []
            size = 0
            while True:
                self.tick()
                raw = os.read(
                    handle, min(65536, FILE_LIMIT + 1 - size, READ_LIMIT + 1 - self.total)
                )
                size += len(raw)
                self.total += len(raw)
                if size > FILE_LIMIT or self.total > READ_LIMIT:
                    raise Refusal("E_LIMIT")
                if not raw:
                    break
                chunks.append(raw)
            after = os.fstat(handle)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise Refusal("E_PATH")
            check = self._open(normalized)
            try:
                current = os.fstat(check)
                if (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino):
                    raise Refusal("E_PATH")
            finally:
                self._close(check)
            payload = b"".join(chunks)
            self.sources[normalized] = digest(payload)
            self.source_digests[normalized] = digest(payload)
            return payload
        finally:
            self._close(handle)

    def validate_json(self, text):
        parse_json(text.encode("utf-8") if isinstance(text, str) else text)


def bundled(relative):
    allowed = {"ontology/scripts/ontology_check.py", "ontology/references/common-contract.json",
               "shared/relations_query.py"}
    if relative not in allowed:
        raise Refusal("E_PATH")
    handle = None
    ancestors = []
    try:
        before_root = PACKAGE.stat()
        if sys.platform == "win32":
            windows_root(str(PACKAGE))
            handles = windows_walk(Path(PACKAGE.anchor), (PACKAGE / relative).parts[1:])
            handle, ancestors = handles[-1], handles[:-1]
            pinned = os.fstat(handles[len(PACKAGE.parts) - 1])
            if (before_root.st_dev, before_root.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise Refusal("E_PATH")
        else:
            handle = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            parts = (PACKAGE / relative).parts[1:]
            for index, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if index < len(parts) - 1:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=handle)
                os.close(handle)
                handle = child
                if index == len(PACKAGE.parts) - 2:
                    pinned = os.fstat(handle)
                    if (before_root.st_dev, before_root.st_ino) != (pinned.st_dev, pinned.st_ino):
                        raise Refusal("E_PATH")
        before = os.fstat(handle)
        if not stat.S_ISREG(before.st_mode):
            raise Refusal("E_PATH")
        chunks = []
        size = 0
        while size <= FILE_LIMIT:
            raw = os.read(handle, min(65536, FILE_LIMIT + 1 - size))
            if not raw:
                break
            size += len(raw)
            chunks.append(raw)
        payload = b"".join(chunks)
        if len(payload) > FILE_LIMIT:
            raise Refusal("E_LIMIT")
        after = os.fstat(handle)
        if (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ):
            raise Refusal("E_PATH")
        return payload
    except (OSError, ValueError):
        raise Refusal("E_IO") from None
    finally:
        if handle is not None:
            os.close(handle)
        for ancestor in reversed(ancestors):
            os.close(ancestor)


def load_modules():
    class FixedSourceLoader(importlib.machinery.SourceFileLoader):
        def __init__(self, name, relative):
            self.relative = relative
            super().__init__(name, str(PACKAGE / relative))

        def get_code(self, fullname):
            return compile(bundled(self.relative), str(PACKAGE / self.relative), "exec")

    modules = []
    for name, relative in (
        ("mir_mcp_ontology", "ontology/scripts/ontology_check.py"),
        ("mir_mcp_relations", "shared/relations_query.py"),
    ):
        # Source-only loading never consults a .pyc or target import search path.
        loader = FixedSourceLoader(name, relative)
        spec = importlib.util.spec_from_file_location(name, str(PACKAGE / relative), loader=loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


ONTOLOGY, RELATIONS = load_modules()


def string(maximum=4096, minimum=1):
    return {"type": "string", "minLength": minimum, "maxLength": maximum}


def integer(minimum, maximum, default=None):
    schema = {"type": "integer", "minimum": minimum, "maximum": maximum}
    if default is not None:
        schema["default"] = default
    return schema


def choice(values, default=None):
    schema = {"type": "string", "enum": values}
    if default is not None:
        schema["default"] = default
    return schema


def closed(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


def array(items, maximum=None, minimum=None, unique=False):
    value = {"type": "array", "items": items}
    if maximum is not None:
        value["maxItems"] = maximum
    if minimum is not None:
        value["minItems"] = minimum
    if unique:
        value["uniqueItems"] = True
    return value


NULL = {"type": "null"}
BOOL = {"type": "boolean"}
TEXT = string()
STRINGS = array(TEXT)
NULL_TEXT = {"anyOf": [TEXT, NULL]}
ENTRY = closed({"pointer": TEXT, "refs": STRINGS})
FINDING = closed({"code": TEXT, "pointer": TEXT})
OUTPUTS = {
    "ontology_validate": closed(
        {
            "valid": BOOL,
            "contract_version": NULL_TEXT,
            "mapping_version": NULL_TEXT,
            "counts": closed(
                {
                    "errors": integer(0, 100000),
                    "warnings": integer(0, 100000),
                    "refs": integer(0, 100000),
                }
            ),
            "findings": array(FINDING),
        }
    ),
    "ontology_lookup": closed(
        {
            "contract": closed({"id": NULL_TEXT, "version": NULL_TEXT}),
            "matches": array(
                closed(
                    {"pointer": TEXT, "score": integer(0, 100000), "label": TEXT, "refs": STRINGS}
                )
            ),
        }
    ),
    "ontology_impact": closed(
        {
            "affected_entries": array(ENTRY),
            "checks_to_run": STRINGS,
            "stale_refs": array(closed({"pointer": TEXT, "ref": TEXT, "code": TEXT})),
            "undeclared_check_links": array(closed({"pointer": TEXT, "ref": NULL_TEXT})),
            "revalidate": BOOL,
        }
    ),
    "handoff_pins": closed(
        {
            "repository_root": NULL_TEXT,
            "head": NULL_TEXT,
            "dirty": {"anyOf": [BOOL, NULL]},
            "sources": array(
                closed(
                    {
                        "path": TEXT,
                        "revision": NULL_TEXT,
                        "sha256": NULL_TEXT,
                        "modified_vs_head": {"anyOf": [BOOL, NULL]},
                        "revision_kind": TEXT,
                    },
                    ["path", "revision", "sha256", "modified_vs_head"],
                )
            ),
            "mapping_path": NULL_TEXT,
            "mapping_version": NULL_TEXT,
            "mapping_sha256": NULL_TEXT,
            "contract_id": NULL_TEXT,
            "contract_version": NULL_TEXT,
            "contract_sha256": NULL_TEXT,
            "observed_at": TEXT,
            "unknowns": STRINGS,
            "pin_inventory": array(
                closed(
                    {
                        "pin": TEXT,
                        "pointer": TEXT,
                        "kind": TEXT,
                        "required": BOOL,
                        "availability": choice(["available", "unknown"]),
                    }
                )
            ),
        }
    ),
    "relations_query": closed(
        {
            "anchor": TEXT,
            "purpose": TEXT,
            "scope": TEXT,
            "source": closed({"graph": TEXT, "sha256": TEXT}),
            "edges": array(
                closed(
                    {
                        "source": TEXT,
                        "relation": TEXT,
                        "target": TEXT,
                        "source_line": integer(1, 1000000),
                    }
                )
            ),
            "notices": STRINGS,
            "truncated": BOOL,
            "resolved_anchors": STRINGS,
        }
    ),
}


# Literal data: receipt validation reads this assignment without executing the package.
INPUT_SCHEMAS = {
    "ontology_validate": {
        "type": "object",
        "properties": {
            "target_root": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096
            },
            "cursor": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024
            },
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "default": 16
            },
            "scope": {
                "type": "string",
                "enum": [
                    "contract",
                    "mapping",
                    "both"
                ],
                "default": "both"
            }
        },
        "required": [
            "target_root"
        ],
        "additionalProperties": False
    },
    "ontology_lookup": {
        "type": "object",
        "properties": {
            "target_root": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096
            },
            "cursor": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024
            },
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "default": 16
            },
            "query": {
                "type": "string",
                "minLength": 1,
                "maxLength": 256
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 16,
                "default": 3
            }
        },
        "required": [
            "target_root",
            "query"
        ],
        "additionalProperties": False
    },
    "ontology_impact": {
        "type": "object",
        "properties": {
            "target_root": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096
            },
            "cursor": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024
            },
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "default": 16
            },
            "paths": {
                "type": "array",
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4096
                },
                "maxItems": 64,
                "minItems": 1,
                "uniqueItems": True
            }
        },
        "required": [
            "target_root",
            "paths"
        ],
        "additionalProperties": False
    },
    "handoff_pins": {
        "type": "object",
        "properties": {
            "target_root": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096
            },
            "cursor": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024
            },
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "default": 16
            },
            "paths": {
                "type": "array",
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4096
                },
                "maxItems": 16,
                "minItems": 1,
                "uniqueItems": True
            }
        },
        "required": [
            "target_root",
            "paths"
        ],
        "additionalProperties": False
    },
    "relations_query": {
        "type": "object",
        "properties": {
            "target_root": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096
            },
            "cursor": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024
            },
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "default": 16
            },
            "adapter": {
                "type": "string",
                "enum": [
                    "yaml"
                ],
                "default": "yaml"
            },
            "graph": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096,
                "default": "spec/graph.yaml"
            },
            "anchor": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096
            },
            "purpose": {
                "type": "string",
                "enum": [
                    "implementation",
                    "verification",
                    "impact",
                    "dependencies"
                ]
            },
            "depth": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4
            },
            "max_edges": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "default": 16
            }
        },
        "required": [
            "target_root",
            "anchor",
            "purpose"
        ],
        "additionalProperties": False
    }
}


def definition(name, description):
    result = closed(
        {
            "ok": BOOL,
            "data": {"anyOf": [OUTPUTS[name], NULL, closed({"unknowns": STRINGS})]},
            "error": {"anyOf": [closed({"code": choice(ERRORS)}), NULL]},
            "next_cursor": {"anyOf": [string(1024), NULL]},
            "profile_protections": choice(["available", "unavailable"]),
        }
    )
    return {
        "name": name,
        "description": description,
        "inputSchema": INPUT_SCHEMAS[name],
        "outputSchema": result,
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    }


TOOLS = [
    definition(
        "ontology_validate",
        "Validate the common contract and target mapping.",
    ),
    definition(
        "ontology_lookup",
        "Find term-matching map entries and declared evidence.",
    ),
    definition(
        "ontology_impact",
        "Select declared affected entries and checks for changed paths.",
    ),
    definition(
        "handoff_pins",
        "Collect repository, source, mapping, and contract pins with availability.",
    ),
    definition(
        "relations_query",
        "Retrieve bounded declared YAML relations for one known anchor.",
    ),
]
TOOL_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def validate(value, schema):
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict) or any(key not in value for key in schema["required"]):
            raise Refusal("E_SCHEMA")
        if set(value) - set(schema["properties"]):
            raise Refusal("E_SCHEMA")
        for key, item in value.items():
            validate(item, schema["properties"][key])
    elif kind == "string":
        if not isinstance(value, str):
            raise Refusal("E_SCHEMA")
        length = len(value.encode("utf-8"))
        if not schema.get("minLength", 0) <= length <= schema.get("maxLength", 4096):
            raise Refusal("E_SCHEMA")
    elif kind == "integer":
        if type(value) is not int or not schema["minimum"] <= value <= schema["maximum"]:
            raise Refusal("E_SCHEMA")
    elif kind == "array":
        if (
            not isinstance(value, list)
            or len(value) < schema.get("minItems", 0)
            or len(value) > schema.get("maxItems", 100000)
        ):
            raise Refusal("E_SCHEMA")
        for item in value:
            validate(item, schema["items"])
        if schema.get("uniqueItems") and len({compact(item) for item in value}) != len(value):
            raise Refusal("E_SCHEMA")
    if "enum" in schema and value not in schema["enum"]:
        raise Refusal("E_SCHEMA")


def git_preflight(io):
    """Check fixed metadata before spawning; child reads are not Guard reads."""
    io.tick()
    try:
        # Guard refuses symlinks on every component, including internal links.
        metadata = io.path(".git")
        if not metadata.is_dir():
            return False
        for relative in (
            ".git/objects", ".git/refs", ".git/objects/info", ".git/HEAD",
            ".git/index", ".git/packed-refs", ".git/shallow",
        ):
            io.path(relative, allow_missing=True)
        for relative in (
            ".git/commondir", ".git/objects/info/alternates",
            ".git/objects/info/http-alternates", ".git/config.worktree",
            ".git/modules", ".gitmodules",
        ):
            if io.exists(relative):
                return False
        head = io.read(".git/HEAD").decode("ascii").strip()
        if head.startswith("ref: "):
            reference = relative_path(head[5:])
            if not reference.startswith("refs/"):
                return False
            io.path(".git/" + reference, allow_missing=True)
        elif not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
            return False
        config = io.read(".git/config").decode("utf-8")
        section = None
        for line in config.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")):
                continue
            # Refuse continuations rather than interpret a second config dialect.
            if stripped.endswith("\\"):
                return False
            if stripped.startswith("["):
                match = re.fullmatch(
                    r'\[\s*([A-Za-z0-9.-]+)(?:\s+"(?:[^"\\]|\\.)*")?\s*\]\s*(?:[#;].*)?',
                    stripped,
                )
                if match is None:
                    return False
                section = match[1].lower().split(".", 1)[0]
                if section in ("include", "includeif", "filter", "submodule"):
                    return False
            else:
                match = re.fullmatch(r"([A-Za-z][A-Za-z0-9-]*)\s*(?:=.*)?", stripped)
                if section is None or match is None:
                    return False
                key = match[1].lower()
                if (section == "core" and key in ("worktree", "gitdir", "excludesfile")) or (
                    section == "extensions" and key in ("worktreeconfig", "partialclone")
                ) or (section == "remote" and key == "promisor") or (
                    section == "diff" and key == "orderfile"
                ):
                    return False
        return True
    except Refusal as exc:
        if exc.code in ("E_LIMIT", "E_TIMEOUT"):
            raise
        return False
    except (OSError, UnicodeError):
        return False


def threaded_git_output(child, deadline):
    """Bound both Windows pipes without selectors (which only supports sockets there)."""
    output = bytearray()
    lock = threading.Lock()
    changed = threading.Event()
    total = 0
    finished = 0
    error = None

    def read(pipe):
        nonlocal total, finished, error
        try:
            while True:
                raw = os.read(pipe.fileno(), 8192)
                if not raw:
                    break
                with lock:
                    total += len(raw)
                    if total > GIT_OUTPUT_LIMIT:
                        error = "E_LIMIT"
                        break
                    if pipe is child.stdout:
                        output.extend(raw)
        except OSError:
            with lock:
                error = error or "E_GIT"
        finally:
            with lock:
                finished += 1
                changed.set()

    readers = [threading.Thread(target=read, args=(pipe,), daemon=True)
               for pipe in (child.stdout, child.stderr)]
    try:
        for reader in readers:
            reader.start()
        while True:
            with lock:
                if error:
                    raise Refusal(error)
                if finished == 2:
                    break
                changed.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not changed.wait(remaining):
                raise Refusal("E_TIMEOUT")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Refusal("E_TIMEOUT")
        return output, child.wait(timeout=remaining)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        for reader in readers:
            if reader.ident is not None:
                reader.join(timeout=1)


def run_git(io, label, *suffix, windows=None):
    """Run one fixed Git query and expose only a commit or a boolean."""
    windows = sys.platform == "win32" if windows is None else windows
    io.tick()
    deadline = io.deadline - GIT_RESERVE
    if time.monotonic() >= deadline:
        raise Refusal("E_TIMEOUT")
    if suffix == ("rev-parse", "--verify", "HEAD"):
        kind = "head"
    elif suffix == (
        "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=all"
    ):
        kind = "status"
    elif len(suffix) == 5 and suffix[:4] == ("log", "-1", "--format=%H", "--"):
        kind = "log"
    elif len(suffix) == 8 and suffix[:7] == (
        "diff", "--quiet", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all",
        "HEAD", "--"
    ):
        kind = "diff"
    else:
        raise Refusal("E_GIT")
    if kind in ("log", "diff"):
        try:
            if relative_path(suffix[-1]) != suffix[-1]:
                raise Refusal("E_GIT")
            io.path(suffix[-1], allow_missing=True)
        except Refusal:
            raise Refusal("E_GIT") from None
    if not git_preflight(io):
        raise Refusal("E_GIT")
    child = None
    try:
        child = subprocess.Popen(
            [*GIT_PREFIX, "-C", str(io.root), *suffix],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, env=dict(GIT_ENV),
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
        )
        if windows:
            output, code = threaded_git_output(child, deadline)
        else:
            output = bytearray()
            total = 0
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                selector.register(child.stderr, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise Refusal("E_TIMEOUT")
                    for key, _ in selector.select(remaining):
                        raw = os.read(key.fileobj.fileno(), 8192)
                        total += len(raw)
                        if total > GIT_OUTPUT_LIMIT:
                            raise Refusal("E_LIMIT")
                        if not raw:
                            selector.unregister(key.fileobj)
                        elif key.fileobj is child.stdout:
                            output.extend(raw)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Refusal("E_TIMEOUT")
                code = child.wait(timeout=remaining)
        if kind == "diff":
            return bool(code) if code in (0, 1) else None
        if code != 0:
            return None
        if kind == "status":
            return bool(output)
        commit = output.decode("ascii").strip()
        if kind == "log" and not commit:
            return ""
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise Refusal("E_GIT")
        return commit
    except subprocess.TimeoutExpired:
        raise Refusal("E_TIMEOUT") from None
    except (OSError, UnicodeError):
        raise Refusal("E_GIT") from None
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait()
            child.stdout.close()
            child.stderr.close()


def guarded_refs(mapping, io):
    for at, entry in ONTOLOGY.map_entries(mapping):
        for _, ref in ONTOLOGY.entry_refs(entry, at):
            io.path(ONTOLOGY.ref_path(ref), allow_missing=True)


def tool_data(name, args, io):
    contract_raw = bundled("ontology/references/common-contract.json")
    contract = parse_json(contract_raw)
    if name == "relations_query":
        return RELATIONS.query_relations(
            args["anchor"],
            args["purpose"],
            root=io.root,
            graph=args.get("graph", "spec/graph.yaml"),
            depth=args.get("depth"),
            max_edges=args.get("max_edges", 16),
            io=io,
        )
    mapping_raw = None
    mapping = None
    if name != "ontology_validate" or args.get("scope", "both") != "contract":
        if name == "handoff_pins" and not io.exists(".mir/ontology-map.json"):
            mapping = {}
        else:
            mapping_raw = io.read(".mir/ontology-map.json")
            mapping = parse_json(mapping_raw)
            if not isinstance(mapping, dict):
                raise Refusal("E_FORMAT")
        if not isinstance(mapping.get("contract", {}), dict):
            raise Refusal("E_FORMAT")
        declaration = mapping.get("contract", {})
        if any(key in declaration and not isinstance(declaration[key], str)
               for key in ("id", "version", "version_range", "sha256")):
            raise Refusal("E_FORMAT")
        guarded_refs(mapping, io)
    if name == "ontology_validate":
        checker = ONTOLOGY.Checker(io=io)
        checker.contract(contract)
        if args.get("scope", "both") != "contract":
            checker.mapping(mapping, contract, contract_raw, io.root)
        findings = [
            {"code": item.get("code", "E_VALIDATION"), "pointer": item["pointer"]}
            for item in checker.errors + checker.warnings
        ]
        return {
            "valid": not checker.errors,
            "contract_version": contract.get("version"),
            "mapping_version": mapping.get("contract", {}).get("version") if mapping else None,
            "counts": {
                "errors": len(checker.errors),
                "warnings": len(checker.warnings),
                "refs": len(checker.checked_refs),
            },
            "findings": findings,
        }
    if name == "ontology_lookup":
        result = ONTOLOGY.lookup(mapping, args["query"], args.get("limit", 3), io=io)
        matches = []
        for item in result["matches"]:
            entry = item["entry"]
            label = (
                entry.get("name") or entry.get("label") or item["pointer"]
                if isinstance(entry, dict)
                else item["pointer"]
            )
            matches.append(
                {
                    "pointer": item["pointer"],
                    "score": item["score"],
                    "label": label if isinstance(label, str) else item["pointer"],
                    "refs": item["evidence"],
                }
            )
        return {
            "contract": {key: mapping.get("contract", {}).get(key) for key in ("id", "version")},
            "matches": matches,
        }
    if name == "ontology_impact":
        result = ONTOLOGY.impact(mapping, io.root, args["paths"], io=io)
        return {
            "affected_entries": result["affected_entries"],
            "checks_to_run": result["checks_to_run"],
            "stale_refs": [
                {"pointer": item["pointer"], "ref": item["ref"], "code": "E_REF"}
                for item in result["stale_refs"]
            ],
            "undeclared_check_links": [
                {"pointer": item["pointer"], "ref": item.get("ref")}
                for item in result["undeclared_check_links"]
            ],
            "revalidate": result["revalidate"],
        }
    report = {
        "mapping_path": ".mir/ontology-map.json" if mapping_raw is not None else None,
        "mapping_version": mapping.get("contract", {}).get("version"),
        "mapping_sha256": digest(mapping_raw) if mapping_raw is not None else None,
        "contract_id": contract.get("contract_id"),
        "contract_version": contract.get("version"),
        "contract_sha256": digest(contract_raw),
    }
    io.git_error = None
    try:
        preflight = None if git_preflight(io) else "E_GIT"
    except Refusal as exc:
        preflight = exc.code
    failures = {}
    codes = []

    def git(label, *suffix):
        if preflight is not None:
            failures[label] = preflight
            return None
        start = time.monotonic()
        try:
            result = run_git(io, label, *suffix)
            code = "E_GIT"
        except Refusal as exc:
            result, code = None, exc.code
        codes.append(None if result is not None else code)
        if result is None:
            failures[label] = f"{code} after {time.monotonic() - start:.2f} s"
        return result

    pins = ONTOLOGY.handoff_pins(io.root, args["paths"], report, io=io, git_runner=git)
    failed = {
        label + ": git command failed": label + ": " + reason
        for label, reason in failures.items()
    }
    pins["unknowns"] = [failed.get(item, item) for item in pins["unknowns"]]
    # One failed query costs only its own pin; the call fails only when Git never answered.
    if preflight is not None or None not in codes:
        io.git_error = preflight or codes[0]
    return pins


PAGE_KEYS = {
    "ontology_validate": ("findings",),
    "ontology_lookup": ("matches",),
    "ontology_impact": (
        "affected_entries", "checks_to_run", "stale_refs", "undeclared_check_links"
    ),
    "handoff_pins": ("sources",),
    "relations_query": ("edges", "notices", "resolved_anchors"),
}


def execute(name, arguments):
    io = None
    unknowns = None
    profile = "unavailable" if tomllib is None else "available"
    try:
        if not isinstance(name, str) or name not in TOOL_BY_NAME:
            raise Refusal("E_SCHEMA")
        validate(arguments, TOOL_BY_NAME[name]["inputSchema"])
        io = Guard(arguments["target_root"])
        profile = io.profile_protections
        args = dict(arguments)
        cursor = args.pop("cursor", None)
        for key in ("paths",):
            if key in args:
                for path in args[key]:
                    io.path(path, allow_missing=True)
        if "graph" in args:
            io.path(args["graph"], allow_missing=True)
        data = tool_data(name, args, io)
        io.tick()
        bounded_structure(data)
        binding = digest(
            compact(
                {
                    "tool": name,
                    "root": str(io.root),
                    "args": args,
                    "sources": io.sources,
                    "source_digests": io.source_digests,
                    "contract": digest(bundled("ontology/references/common-contract.json")),
                }
            ).encode()
        )
        offset = 0
        if cursor is not None:
            try:
                decoded = parse_json(
                    base64.b64decode(cursor.encode(), altchars=b"-_", validate=True)
                )
                if (
                    set(decoded) != {"h", "o"}
                    or decoded["h"] != binding
                    or type(decoded["o"]) is not int
                    or decoded["o"] <= 0
                ):
                    raise Refusal("E_CURSOR")
                offset = decoded["o"]
            except (ValueError, UnicodeError, TypeError, KeyError, Refusal):
                raise Refusal("E_CURSOR") from None
        keys = PAGE_KEYS[name]
        count = max(len(data[key]) for key in keys)
        if offset and offset >= count:
            raise Refusal("E_CURSOR")
        end = min(offset + args.get("page_size", 16), count)
        while True:
            page = dict(data)
            for key in keys:
                page[key] = data[key][offset:end]
            if name == "handoff_pins":
                page = ONTOLOGY.finalize_handoff_pins(page, args["paths"][offset:end])
            next_cursor = None
            if end < count:
                next_cursor = base64.urlsafe_b64encode(
                    compact({"h": binding, "o": end}).encode()
                ).decode()
            result = {
                "ok": getattr(io, "git_error", None) is None,
                "data": page,
                "error": {"code": io.git_error} if getattr(io, "git_error", None) else None,
                "next_cursor": next_cursor,
                "profile_protections": profile,
            }
            # Reserve space for the JSON-RPC id and modern result envelope.
            if len(compact(result).encode()) <= OUTPUT_LIMIT - 1024:
                return result
            if end - offset <= 1:
                raise Refusal("E_LIMIT")
            end -= 1
    except Refusal as exc:
        code = exc.code
        unknowns = exc.unknowns
    except RELATIONS.RelationsError as exc:
        code = exc.code
    except (OSError, UnicodeError):
        code = "E_IO"
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, RuntimeError):
        code = "E_FORMAT"
    finally:
        if io is not None:
            io.close()
    return {
        "ok": False,
        "data": {"unknowns": unknowns} if unknowns is not None else None,
        "error": {"code": code},
        "next_cursor": None,
        "profile_protections": profile,
    }


def rpc_error(identity, numeric, code, **extra):
    return {
        "jsonrpc": "2.0",
        "id": identity,
        "error": {"code": numeric, "message": code, "data": {"code": code, **extra}},
    }


def timeout_handler(signum, frame):
    raise Refusal("E_TIMEOUT")


class Protocol:
    def __init__(self, windows=None):
        self.windows = sys.platform == "win32" if windows is None else windows
        self.exit_after_response = False
        self.initialized = False
        self.pending = False

    def request(self, request):
        identity = None
        requested = ""
        try:
            if not isinstance(request, dict):
                raise Refusal("E_SCHEMA")
            identity = request.get("id")
            if (
                ("id" in request and type(identity) not in (str, int))
                or (isinstance(identity, str) and len(identity.encode()) > 256)
                or (type(identity) is int and abs(identity) > 9007199254740991)
            ):
                identity = None
                raise Refusal("E_SCHEMA")
            if (
                request.get("jsonrpc") != "2.0"
                or not isinstance(request.get("method"), str)
                or set(request) - {"jsonrpc", "id", "method", "params"}
            ):
                raise Refusal("E_SCHEMA")
            method = request["method"]
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise Refusal("E_SCHEMA")
            if "_meta" in params and not isinstance(params["_meta"], dict):
                raise Refusal("E_SCHEMA")
            if method == "notifications/initialized":
                if "id" in request or not self.pending or params:
                    raise Refusal("E_SCHEMA")
                self.initialized = True
                self.pending = False
                return None
            if "id" not in request:
                return None
            if method == "initialize":
                if self.initialized or self.pending:
                    raise Refusal("E_SCHEMA")
                if not isinstance(params.get("protocolVersion"), str):
                    raise Refusal("E_SCHEMA")
                if (
                    set(params) - {"protocolVersion", "clientInfo", "capabilities", "_meta"}
                    or not isinstance(params.get("clientInfo"), dict)
                    or any(not isinstance(params["clientInfo"].get(key), str)
                           for key in ("name", "version"))
                    or not isinstance(params.get("capabilities"), dict)
                ):
                    raise Refusal("E_SCHEMA")
                self.pending = True
                return {
                    "jsonrpc": "2.0",
                    "id": identity,
                    "result": {
                        "protocolVersion": LEGACY,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "mir-mcp", "version": VERSION},
                    },
                }
            meta = params.get("_meta")
            modern = "_meta" in params and not (
                self.initialized
                and isinstance(meta, dict)
                and "io.modelcontextprotocol/protocolVersion" not in meta
            )
            if modern:
                if not isinstance(meta, dict):
                    raise Refusal("E_SCHEMA")
                if "io.modelcontextprotocol/protocolVersion" not in meta:
                    raise Refusal("E_SCHEMA")
                if not isinstance(meta["io.modelcontextprotocol/protocolVersion"], str):
                    raise Refusal("E_SCHEMA")
                requested = meta["io.modelcontextprotocol/protocolVersion"]
                if requested != MODERN:
                    raise Refusal("E_VERSION")
                info = meta.get("io.modelcontextprotocol/clientInfo")
                if "io.modelcontextprotocol/clientInfo" in meta and (
                    not isinstance(info, dict)
                    or any(not isinstance(info.get(key), str) for key in ("name", "version"))
                ):
                    raise Refusal("E_SCHEMA")
                if not isinstance(meta.get("io.modelcontextprotocol/clientCapabilities"), dict):
                    raise Refusal("E_SCHEMA")
            elif not self.initialized:
                raise Refusal("E_VERSION")
            ordinary = {key: value for key, value in params.items() if key != "_meta"}
            if method == "server/discover" and modern and not ordinary:
                result = {
                    "supportedVersions": VERSIONS,
                    "capabilities": {"tools": {}},
                    "_meta": {
                        "io.modelcontextprotocol/serverInfo": {
                            "name": "mir-mcp",
                            "version": VERSION,
                        }
                    },
                }
            elif method == "tools/list" and not ordinary:
                result = {"tools": TOOLS}
            elif method == "tools/call" and set(ordinary) == {"name", "arguments"}:
                if self.windows:
                    completed = []
                    def call():
                        completed.append(execute(ordinary["name"], ordinary["arguments"]))
                    worker = threading.Thread(target=call, daemon=True)
                    worker.start()
                    worker.join(10)
                    if worker.is_alive():
                        structured = {
                            "ok": False, "data": None, "error": {"code": "E_TIMEOUT"},
                            "next_cursor": None,
                            "profile_protections": (
                                "unavailable" if tomllib is None else "available"
                            ),
                        }
                        self.exit_after_response = True
                    else:
                        structured = completed[0]
                else:
                    signal.setitimer(signal.ITIMER_REAL, 10)
                    try:
                        structured = execute(ordinary["name"], ordinary["arguments"])
                    finally:
                        signal.setitimer(signal.ITIMER_REAL, 0)
                result = {
                    "content": [],
                    "structuredContent": structured,
                    "isError": not structured["ok"],
                }
                if result["isError"]:
                    reason = {"code": structured["error"]["code"]}
                    if "unknowns" in (structured["data"] or {}):
                        reason["unknowns"] = list(structured["data"]["unknowns"])
                    # Fit the escaped text inside the envelope space execute() reserves.
                    while len(compact(compact(reason)).encode()) > 512:
                        reason["unknowns"].pop()
                        reason["omitted"] = reason.get("omitted", 0) + 1
                    result["content"] = [{"type": "text", "text": compact(reason)}]
            elif method in ("tools/list", "tools/call", "server/discover"):
                raise Refusal("E_SCHEMA")
            else:
                return rpc_error(identity, -32601, "E_SCHEMA")
            if modern:
                result["resultType"] = "complete"
                if method != "tools/call":
                    result["ttlMs"] = 3600000
                    result["cacheScope"] = "public"
            return {"jsonrpc": "2.0", "id": identity, "result": result}
        except Refusal as exc:
            if exc.code == "E_VERSION":
                response = rpc_error(
                    identity, -32022, exc.code, supported=VERSIONS, requested=requested
                )
                response["error"]["message"] = "Unsupported protocol version"
                return response
            return rpc_error(identity, -32602, exc.code)


def main(windows=None):
    if sys.version_info < (3, 11):  # noqa: UP036 - standalone refusal must run on 3.9
        running = ".".join(map(str, sys.version_info[:3]))
        sys.stderr.write("mir-mcp requires Python 3.11+; running " + running + "\n")
        return 1
    windows = sys.platform == "win32" if windows is None else windows
    if not windows:
        signal.signal(signal.SIGALRM, timeout_handler)
    protocol = Protocol(windows=windows)
    while True:
        raw = sys.stdin.buffer.readline(FRAME_LIMIT + 1)
        if not raw:
            return 0
        if len(raw) > FRAME_LIMIT:
            while raw and not raw.endswith(b"\n"):
                raw = sys.stdin.buffer.readline(FRAME_LIMIT + 1)
            response = rpc_error(None, -32600, "E_LIMIT")
        else:
            try:
                response = protocol.request(parse_json(raw))
            except Refusal as exc:
                response = rpc_error(None, -32700 if exc.code == "E_FORMAT" else -32600, exc.code)
            except (UnicodeError, ValueError, TypeError, KeyError):
                response = rpc_error(None, -32700, "E_FORMAT")
        if response is not None:
            try:
                bounded_structure(response)
                encoded = compact(response).encode("utf-8")
                if len(encoded) + 1 > OUTPUT_LIMIT:
                    response = rpc_error(response.get("id"), -32603, "E_LIMIT")
                    encoded = compact(response).encode("utf-8")
                sys.stdout.buffer.write(encoded + b"\n")
                sys.stdout.buffer.flush()
                if protocol.exit_after_response:
                    os._exit(0)
            except (BrokenPipeError, OSError):
                return 0


if __name__ == "__main__":
    sys.exit(main())
