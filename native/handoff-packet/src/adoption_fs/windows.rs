//! Owned handle boundary. Only a validated volume/share anchor is opened by path.
use super::*;
use std::{
    mem::{size_of, size_of_val},
    os::windows::{
        ffi::OsStrExt,
        io::{AsRawHandle, FromRawHandle},
    },
    path::Prefix,
    ptr::{null, null_mut},
};
use windows_sys::{
    Wdk::{
        Foundation::OBJECT_ATTRIBUTES,
        Storage::FileSystem::{
            FILE_CREATE, FILE_DIRECTORY_FILE, FILE_NON_DIRECTORY_FILE, FILE_OPEN, FILE_OPEN_IF,
            FILE_OPEN_REPARSE_POINT, FILE_RENAME_INFORMATION, FILE_RENAME_POSIX_SEMANTICS,
            FILE_RENAME_REPLACE_IF_EXISTS, FILE_SYNCHRONOUS_IO_NONALERT, FileRenameInformationEx,
            NtCreateFile, NtSetInformationFile,
        },
    },
    Win32::{
        Foundation::{
            INVALID_HANDLE_VALUE, OBJ_CASE_INSENSITIVE, RtlNtStatusToDosError, UNICODE_STRING,
        },
        Storage::FileSystem::*,
        System::{IO::IO_STATUS_BLOCK, SystemServices::FILE_CS_FLAG_CASE_SENSITIVE_DIR},
    },
};

fn invalid() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, "invalid Windows mutation path")
}

fn name(value: &OsStr) -> io::Result<Vec<u16>> {
    let units: Vec<_> = value.encode_wide().collect();
    if units.is_empty()
        || units.len() > (u16::MAX / 2) as usize
        || units
            .iter()
            .any(|u| *u < 32 || [34, 42, 47, 58, 60, 62, 63, 92, 124].contains(u))
        || matches!(units.last(), Some(32 | 46))
    {
        return Err(invalid());
    }
    let mut stem: Vec<_> = units
        .iter()
        .copied()
        .take_while(|u| *u != 46)
        .map(|u| if (97..=122).contains(&u) { u - 32 } else { u })
        .collect();
    while stem.last() == Some(&32) {
        stem.pop();
    }
    let reserved = ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
        .iter()
        .any(|s| stem.iter().copied().eq(s.encode_utf16()));
    let port = stem.len() == 4
        && (stem[..3] == [67, 79, 77] || stem[..3] == [76, 80, 84])
        && ((49..=57).contains(&stem[3]) || [0xb9, 0xb2, 0xb3].contains(&stem[3]));
    if reserved || port {
        return Err(invalid());
    }
    Ok(units)
}

fn wide(value: &OsStr) -> Vec<u16> {
    value.encode_wide().chain(Some(0)).collect()
}

fn query_device(value: &OsStr) -> io::Result<Vec<u16>> {
    let value = wide(value);
    let mut result = vec![0; 32768];
    // SAFETY: terminated input and writable output of the advertised length.
    if unsafe { QueryDosDeviceW(value.as_ptr(), result.as_mut_ptr(), result.len() as u32) } == 0 {
        return Err(io::Error::last_os_error());
    }
    result.truncate(result.iter().position(|u| *u == 0).unwrap_or(result.len()));
    Ok(result)
}

fn drive_anchor(drive: u8) -> io::Result<OsString> {
    let device = query_device(OsStr::new(&format!("{}:", drive as char)))?;
    let prefix: Vec<_> = r"\Device\HarddiskVolume".encode_utf16().collect();
    if !device.starts_with(&prefix)
        || device.len() == prefix.len()
        || !device[prefix.len()..].iter().all(|u| (48..=57).contains(u))
    {
        return Err(invalid()); // SUBST and arbitrary device mappings are not anchors.
    }
    let mount = wide(OsStr::new(&format!("{}:\\", drive as char)));
    let mut volume = [0; 50];
    // SAFETY: terminated drive root; output accommodates a volume GUID root.
    if unsafe {
        GetVolumeNameForVolumeMountPointW(mount.as_ptr(), volume.as_mut_ptr(), volume.len() as u32)
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    let end = volume.iter().position(|u| *u == 0).ok_or_else(invalid)?;
    use std::os::windows::ffi::OsStringExt;
    let anchor = OsString::from_wide(&volume[..end]);
    let volume_name = volume.get(4..end.saturating_sub(1)).ok_or_else(invalid)?;
    // A mapping change between the two queries must not select another volume.
    if query_device(&OsString::from_wide(volume_name))? != device {
        return Err(invalid());
    }
    Ok(anchor)
}

fn anchor(root: &Path) -> io::Result<(OsString, Vec<&OsStr>)> {
    if !root.is_absolute() {
        return Err(invalid());
    }
    let raw: Vec<_> = root.as_os_str().encode_wide().collect();
    if raw
        .split(|u| [47, 92].contains(u))
        .any(|c| c == [46] || c == [46, 46])
    {
        return Err(invalid());
    }
    let mut components = root.components();
    let Some(Component::Prefix(prefix)) = components.next() else {
        return Err(invalid());
    };
    if components.next() != Some(Component::RootDir) {
        return Err(invalid());
    }
    let mut parts = Vec::new();
    for part in components {
        let Component::Normal(part) = part else {
            return Err(invalid());
        };
        name(part)?;
        parts.push(part);
    }
    let anchor = match prefix.kind() {
        Prefix::Disk(drive) | Prefix::VerbatimDisk(drive) => drive_anchor(drive)?,
        Prefix::UNC(server, share) | Prefix::VerbatimUNC(server, share) => {
            name(server)?;
            name(share)?;
            let mut result = OsString::from(r"\\?\UNC\");
            result.push(server);
            result.push("\\");
            result.push(share);
            result.push("\\");
            result
        }
        Prefix::Verbatim(volume) => {
            let units: Vec<_> = volume.encode_wide().collect();
            let prefix: Vec<_> = "Volume{".encode_utf16().collect();
            if units.len() != 44
                || !units.starts_with(&prefix)
                || units[43] != 125
                || !(7..43).all(|i| {
                    if [15, 20, 25, 30].contains(&i) {
                        units[i] == 45
                    } else {
                        matches!(units[i], 48..=57 | 65..=70 | 97..=102)
                    }
                })
            {
                return Err(invalid());
            }
            let mut result = OsString::from(r"\\?\");
            result.push(volume);
            result.push("\\");
            result
        }
        _ => return Err(invalid()),
    };
    Ok((anchor, parts))
}

fn information<T: Default>(file: &File, class: FILE_INFO_BY_HANDLE_CLASS) -> io::Result<T> {
    let mut result = T::default();
    // SAFETY: callers pair the class with its exact repr(C) record; live handle
    // and a writable buffer of the record's full size, borrowed for this call.
    if unsafe {
        GetFileInformationByHandleEx(
            file.as_raw_handle(),
            class,
            (&mut result as *mut T).cast(),
            size_of::<T>() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(result)
}

fn directory(file: File) -> io::Result<File> {
    let info: FILE_ATTRIBUTE_TAG_INFO = information(&file, FileAttributeTagInfo)?;
    // SAFETY: borrowed live handle; GetFileType does not take ownership.
    if unsafe { GetFileType(file.as_raw_handle()) } != FILE_TYPE_DISK
        || info.FileAttributes & FILE_ATTRIBUTE_DIRECTORY == 0
        || info.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0
    {
        return Err(io::Error::other(
            "mutation parent is not a non-reparse disk directory",
        ));
    }
    Ok(file)
}

fn open_relative(
    parent: &File,
    value: &OsStr,
    access: u32,
    disposition: u32,
    options: u32,
) -> io::Result<File> {
    open_counted(parent, &mut name(value)?, access, disposition, options)
}

fn open_counted(
    parent: &File,
    units: &mut [u16],
    access: u32,
    disposition: u32,
    options: u32,
) -> io::Result<File> {
    let length = (units.len() * 2) as u16; // name checked length; empty reopens parent.
    let string = UNICODE_STRING {
        Length: length,
        MaximumLength: length,
        Buffer: units.as_mut_ptr(),
    };
    let case: FILE_CASE_SENSITIVE_INFO = information(parent, FileCaseSensitiveInfo)?;
    let attributes = OBJECT_ATTRIBUTES {
        Length: size_of::<OBJECT_ATTRIBUTES>() as u32,
        RootDirectory: parent.as_raw_handle(),
        ObjectName: &string,
        Attributes: if case.Flags & FILE_CS_FLAG_CASE_SENSITIVE_DIR != 0 {
            0
        } else {
            OBJ_CASE_INSENSITIVE
        },
        ..Default::default()
    };
    let mut handle = null_mut();
    let mut status_block = IO_STATUS_BLOCK::default();
    // SAFETY: all pointers live through this synchronous call; a validated
    // single component (or empty self-open) is relative to a live, no-reparse directory.
    // Attributes excludes OBJ_INHERIT; no asynchronous completion is possible.
    let status = unsafe {
        NtCreateFile(
            &mut handle,
            access | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
            &attributes,
            &mut status_block,
            null(),
            0,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            disposition,
            options | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
            null(),
            0,
        )
    };
    if status < 0 {
        // SAFETY: pure NTSTATUS conversion, immediately preserving this failure.
        return Err(io::Error::from_raw_os_error(
            unsafe { RtlNtStatusToDosError(status) } as i32,
        ));
    }
    // SAFETY: successful NtCreateFile returned one new owned, non-inheritable
    // handle. File closes it on every path, including validation failure.
    Ok(unsafe { File::from_raw_handle(handle) })
}

fn open_directory(parent: &File, value: &OsStr) -> io::Result<File> {
    directory(open_relative(
        parent,
        value,
        FILE_TRAVERSE,
        FILE_OPEN,
        FILE_DIRECTORY_FILE,
    )?)
}

pub(super) fn parent(root: &Path, relative: &Path) -> io::Result<Parent> {
    let raw: Vec<_> = relative.as_os_str().encode_wide().collect();
    if raw
        .split(|u| [47, 92].contains(u))
        .any(|c| c == [46] || c == [46, 46])
    {
        return Err(invalid());
    }
    let (anchor, mut parts) = anchor(root)?;
    for part in relative.components() {
        let Component::Normal(part) = part else {
            return Err(invalid());
        };
        name(part)?;
        parts.push(part);
    }
    let leaf = parts.pop().ok_or_else(invalid)?.to_owned();
    let anchor = wide(&anchor);
    // SAFETY: terminated validated anchor only (never the full root path),
    // null security attributes make the returned handle non-inheritable.
    let handle = unsafe {
        CreateFileW(
            anchor.as_ptr(),
            FILE_TRAVERSE | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            null(),
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: exactly one owner for this successful CreateFileW handle.
    let mut directory = directory(unsafe { File::from_raw_handle(handle) })?;
    for part in parts {
        directory = open_directory(&directory, part)?;
    }
    Ok(Parent {
        directory,
        name: leaf,
    })
}

pub(super) fn file_identity(file: &File) -> io::Result<Identity> {
    let info: FILE_ID_INFO = information(file, FileIdInfo)?;
    Ok(Identity {
        volume: info.VolumeSerialNumber,
        id: info.FileId.Identifier,
    })
}

pub(super) fn object_identity(
    parent: &Parent,
    name: &OsStr,
    directory: bool,
) -> io::Result<Option<Identity>> {
    let file = open_relative(&parent.directory, name, 0, FILE_OPEN, 0)?;
    let info: FILE_ATTRIBUTE_TAG_INFO = information(&file, FileAttributeTagInfo)?;
    // SAFETY: borrowed live handle; the call does not transfer ownership.
    if unsafe { GetFileType(file.as_raw_handle()) } != FILE_TYPE_DISK
        || info.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0
        || (info.FileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0) != directory
    {
        return Ok(None);
    }
    file_identity(&file).map(Some)
}

fn regular(file: File) -> io::Result<File> {
    let info: FILE_ATTRIBUTE_TAG_INFO = information(&file, FileAttributeTagInfo)?;
    // SAFETY: borrowed live handle; no ownership transfer.
    if unsafe { GetFileType(file.as_raw_handle()) } != FILE_TYPE_DISK
        || info.FileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT) != 0
    {
        return Err(io::Error::other("mutation leaf is not a regular disk file"));
    }
    Ok(file)
}

pub(super) fn open(parent: &Parent, write: bool, append: bool) -> io::Result<File> {
    let access = if !write {
        FILE_READ_DATA
    } else if append {
        FILE_APPEND_DATA
    } else {
        FILE_WRITE_DATA
    };
    // No truncation before validation; append deliberately omits WRITE_DATA.
    regular(open_relative(
        &parent.directory,
        &parent.name,
        access,
        if write { FILE_OPEN_IF } else { FILE_OPEN },
        FILE_NON_DIRECTORY_FILE,
    )?)
}

pub(super) fn create(parent: &Parent, name: &OsStr, _mode: u32) -> io::Result<File> {
    // CPython 3.12 Windows create modes inherit DACLs; no POSIX confidentiality claim.
    regular(open_relative(
        &parent.directory,
        name,
        FILE_READ_DATA | FILE_WRITE_DATA | FILE_WRITE_ATTRIBUTES | DELETE,
        FILE_CREATE,
        FILE_NON_DIRECTORY_FILE,
    )?)
}

pub(super) fn mkdir(parent: &Parent, _mode: u32) -> io::Result<()> {
    directory(open_relative(
        &parent.directory,
        &parent.name,
        FILE_TRAVERSE,
        FILE_CREATE,
        FILE_DIRECTORY_FILE,
    )?)
    .map(drop)
}

pub(super) fn rename(source: &Parent, destination: &Parent) -> io::Result<()> {
    // Generic rename uses the current entry, including a substituted reparse
    // entry. OPEN_REPARSE_POINT prevents following it; no READ_DATA is needed.
    let file = open_relative(&source.directory, &source.name, DELETE, FILE_OPEN, 0)?;
    rename_file(&file, destination)
}

pub(super) fn rename_file(file: &File, destination: &Parent) -> io::Result<()> {
    let units = name(&destination.name)?;
    let start = std::mem::offset_of!(FILE_RENAME_INFORMATION, FileName);
    // NT needs at least the full record, including its trailing padding for
    // short names (x64: FileName offset 20, sizeof 24, one WCHAR ends at 22).
    // FileNameLength still counts only the name bytes, without a terminator.
    let bytes = size_of::<FILE_RENAME_INFORMATION>().max(start + units.len() * 2);
    // usize storage aligns the record and rounds up the allocation separately.
    let mut buffer = vec![0usize; bytes.div_ceil(size_of::<usize>())];
    let info = buffer.as_mut_ptr().cast::<FILE_RENAME_INFORMATION>();
    let mut status_block = IO_STATUS_BLOCK::default();
    // FILE_RENAME_INFORMATION (ntifs.h) permits a simple name relative to
    // RootDirectory with DELETE access on the source. Use the NT Ex class (65)
    // directly, retaining the pinned directory across the rename.
    // https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information
    // SAFETY: aligned, zeroed allocation fits the record and complete tail;
    // both handles and all name bytes remain live for the synchronous call.
    let status = unsafe {
        (*info).Anonymous.Flags = FILE_RENAME_REPLACE_IF_EXISTS | FILE_RENAME_POSIX_SEMANTICS;
        (*info).RootDirectory = destination.directory.as_raw_handle();
        (*info).FileNameLength = (units.len() * 2) as u32;
        std::ptr::copy_nonoverlapping(
            units.as_ptr(),
            buffer.as_mut_ptr().cast::<u8>().add(start).cast::<u16>(),
            units.len(),
        );
        NtSetInformationFile(
            file.as_raw_handle(),
            &mut status_block,
            info.cast(),
            bytes as u32,
            FileRenameInformationEx,
        )
    };
    if status < 0 {
        // SAFETY: pure NTSTATUS conversion; Win32 last-error is not set by NT.
        return Err(io::Error::from_raw_os_error(
            unsafe { RtlNtStatusToDosError(status) } as i32,
        ));
    }
    Ok(())
}

pub(super) fn dispose_file(file: &File) -> io::Result<()> {
    let info = FILE_DISPOSITION_INFO_EX {
        Flags: FILE_DISPOSITION_FLAG_DELETE | FILE_DISPOSITION_FLAG_POSIX_SEMANTICS,
    };
    // SAFETY: borrowed DELETE-capable handle and exact repr(C) record. Do not
    // ignore read-only attributes or fall back when the filesystem refuses Ex.
    if unsafe {
        SetFileInformationByHandle(
            file.as_raw_handle(),
            FileDispositionInfoEx,
            (&info as *const FILE_DISPOSITION_INFO_EX).cast(),
            size_of_val(&info) as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

pub(super) fn unlink(parent: &Parent, name: &OsStr, directory: bool) -> io::Result<()> {
    let file = open_relative(&parent.directory, name, DELETE, FILE_OPEN, 0)?;
    let info: FILE_ATTRIBUTE_TAG_INFO = information(&file, FileAttributeTagInfo)?;
    let is_dir = info.FileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0;
    let reparse = info.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0;
    // Inspect the exact deletion handle, closing a file-to-directory swap.
    // Directory cleanup rejects every reparse type; file unlink removes a link
    // itself (including a junction), just as unlinkat never follows its leaf.
    if directory != (is_dir && !reparse) {
        use windows_sys::Win32::Foundation::{ERROR_ACCESS_DENIED, ERROR_DIRECTORY};
        return Err(io::Error::from_raw_os_error(if directory {
            ERROR_DIRECTORY as i32
        } else {
            ERROR_ACCESS_DENIED as i32
        }));
    }
    dispose_file(&file)
}

pub(super) fn sync_file(parent: &File) -> io::Result<File> {
    // FlushFileBuffers requires GENERIC_WRITE. open_counted adds the attributes
    // needed for directory verification; GENERIC_READ would also demand LIST_DIRECTORY.
    directory(open_counted(
        parent,
        &mut [],
        FILE_GENERIC_WRITE,
        FILE_OPEN,
        FILE_DIRECTORY_FILE,
    )?)
}

pub(super) fn directory_empty(parent: &Parent) -> io::Result<bool> {
    let file = directory(open_relative(
        &parent.directory,
        &parent.name,
        FILE_LIST_DIRECTORY,
        FILE_OPEN,
        FILE_DIRECTORY_FILE,
    )?)?;
    // u64 allocation provides FILE_FULL_DIR_INFO alignment; names are counted UTF-16.
    let mut buffer = [0u64; 8192];
    loop {
        // SAFETY: live list-capable handle and aligned writable buffer of stated size.
        if unsafe {
            GetFileInformationByHandleEx(
                file.as_raw_handle(),
                FileFullDirectoryInfo,
                buffer.as_mut_ptr().cast(),
                size_of_val(&buffer) as u32,
            )
        } == 0
        {
            let error = io::Error::last_os_error();
            return if error.raw_os_error()
                == Some(windows_sys::Win32::Foundation::ERROR_NO_MORE_FILES as i32)
            {
                Ok(true)
            } else {
                Err(error)
            };
        }
        let mut offset = 0;
        let base = buffer.as_ptr().cast::<u8>();
        loop {
            let start = std::mem::offset_of!(FILE_FULL_DIR_INFO, FileName);
            if offset + size_of::<FILE_FULL_DIR_INFO>() > size_of_val(&buffer) {
                return Err(io::Error::other("invalid directory information"));
            }
            // SAFETY: the checked record fits; unaligned reads also handle later offsets.
            let info = unsafe {
                base.add(offset)
                    .cast::<FILE_FULL_DIR_INFO>()
                    .read_unaligned()
            };
            let length = info.FileNameLength as usize;
            if !length.is_multiple_of(2) || offset + start + length > size_of_val(&buffer) {
                return Err(io::Error::other("invalid directory name length"));
            }
            // SAFETY: only the first one/two UTF-16 units are read, after length checks.
            let dot = unsafe {
                let name = base.add(offset + start).cast::<u16>();
                (length == 2 && name.read_unaligned() == 46)
                    || (length == 4
                        && name.read_unaligned() == 46
                        && name.add(1).read_unaligned() == 46)
            };
            if !dot {
                return Ok(false);
            }
            if info.NextEntryOffset == 0 {
                break;
            }
            if (info.NextEntryOffset as usize) < start + length {
                return Err(io::Error::other("invalid directory entry offset"));
            }
            offset += info.NextEntryOffset as usize;
        }
    }
}
