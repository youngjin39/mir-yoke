//! Owned handle boundary. Only a validated volume/share anchor is opened by path.
use super::*;
use std::{
    mem::size_of,
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
            FILE_DIRECTORY_FILE, FILE_OPEN, FILE_OPEN_REPARSE_POINT, FILE_SYNCHRONOUS_IO_NONALERT,
            NtCreateFile,
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

fn open_directory(parent: &File, value: &OsStr) -> io::Result<File> {
    let mut units = name(value)?;
    let length = (units.len() * 2) as u16; // name checked counted byte-length overflow.
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
    // single component is relative to a live, no-reparse directory handle.
    // Attributes excludes OBJ_INHERIT; no asynchronous completion is possible.
    let status = unsafe {
        NtCreateFile(
            &mut handle,
            FILE_TRAVERSE | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
            &attributes,
            &mut status_block,
            null(),
            0,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            FILE_OPEN,
            FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
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
    directory(unsafe { File::from_raw_handle(handle) })
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
