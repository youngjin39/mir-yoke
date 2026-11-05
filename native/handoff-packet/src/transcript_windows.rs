//! Stable Win32 handle identity; no path lookup after the file is opened.
use crate::transcript::FileIdentity;
use std::{ffi::c_void, fs::File, io, os::windows::io::AsRawHandle};
#[repr(C)]
#[derive(Default)]
struct FileInformation {
    attributes: u32,
    creation: [u32; 2],
    access: [u32; 2],
    write: [u32; 2],
    volume: u32,
    size_high: u32,
    size_low: u32,
    links: u32,
    index_high: u32,
    index_low: u32,
}
#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetFileInformationByHandle(handle: *mut c_void, info: *mut FileInformation) -> i32;
}
pub(crate) fn identity(file: &File) -> io::Result<FileIdentity> {
    let mut info = FileInformation::default();
    // SAFETY: the borrowed File keeps its handle alive; info has the Win32
    // BY_HANDLE_FILE_INFORMATION layout and is writable for this call.
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0 {
        return Err(io::Error::last_os_error());
    }
    if info.attributes & 0x400 != 0 {
        return Err(io::Error::other("transcript must not be a reparse point"));
    }
    Ok(FileIdentity {
        volume: u64::from(info.volume),
        index: (u64::from(info.index_high) << 32) | u64::from(info.index_low),
    })
}
