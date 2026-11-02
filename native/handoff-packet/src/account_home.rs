//! The sole unsafe boundary: Unix account database lookup, independent of HOME.
//! Layouts match pwd.h on the supported Unix targets (Darwin and Linux).
// Reject unknown ABIs rather than passing an incorrectly sized record to libc.
#[cfg(not(any(target_vendor = "apple", target_os = "linux")))]
compile_error!("account_home requires a reviewed pwd.h layout for this Unix target");
use std::{
    ffi::{CStr, OsStr, c_char, c_int},
    mem::MaybeUninit,
    os::unix::ffi::OsStrExt,
    path::PathBuf,
    ptr,
};

#[repr(C)]
struct Passwd {
    name: *mut c_char,
    passwd: *mut c_char,
    uid: u32,
    gid: u32,
    #[cfg(target_vendor = "apple")]
    change: std::ffi::c_long,
    #[cfg(target_vendor = "apple")]
    class: *mut c_char,
    gecos: *mut c_char,
    dir: *mut c_char,
    shell: *mut c_char,
    #[cfg(target_vendor = "apple")]
    expire: std::ffi::c_long,
}

unsafe extern "C" {
    fn getuid() -> u32;
    fn getpwuid_r(
        uid: u32,
        pwd: *mut Passwd,
        buffer: *mut c_char,
        length: usize,
        result: *mut *mut Passwd,
    ) -> c_int;
}

pub(crate) fn get() -> Option<PathBuf> {
    lookup(1024)
}

fn lookup(mut size: usize) -> Option<PathBuf> {
    // ERANGE is 34 on Darwin and Linux; getpwuid_r returns the error directly.
    const ERANGE: c_int = 34;
    loop {
        let mut buffer = vec![0u8; size];
        let mut pwd = MaybeUninit::<Passwd>::uninit();
        let mut result = ptr::null_mut();
        // SAFETY: pwd has the target's C layout. Both writable allocations and
        // result outlive the call. Read pwd only on success with a non-null result;
        // libc then supplies a NUL-terminated dir inside buffer. Copy its bytes
        // before buffer is dropped. getuid takes no arguments and owns no memory.
        let home = unsafe {
            let status = getpwuid_r(
                getuid(),
                pwd.as_mut_ptr(),
                buffer.as_mut_ptr().cast(),
                buffer.len(),
                &mut result,
            );
            if status == ERANGE {
                None
            } else if status != 0 || result.is_null() {
                return None;
            } else {
                let dir = pwd.assume_init().dir;
                if dir.is_null() {
                    return None;
                }
                Some(PathBuf::from(OsStr::from_bytes(
                    CStr::from_ptr(dir).to_bytes(),
                )))
            }
        };
        if home.is_some() {
            return home;
        }
        size = size.checked_mul(2)?;
    }
}

#[cfg(test)]
#[forbid(unsafe_code)]
mod tests {
    #[test]
    fn grows_small_account_buffer() {
        assert_eq!(super::lookup(1), super::get());
        assert!(super::get().is_some());
    }
}
