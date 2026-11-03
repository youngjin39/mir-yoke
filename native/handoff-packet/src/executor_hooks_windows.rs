//! Minimal Windows Job Object boundary. Child creation stays in safe std code;
//! CREATE_SUSPENDED prevents execution until assignment and thread resumption.
use std::{
    ffi::c_void,
    io,
    mem::{size_of, zeroed},
    os::windows::io::AsRawHandle,
    process::Child,
    ptr,
};

type Handle = *mut c_void;
#[repr(C)]
struct BasicLimits {
    process_time: i64,
    job_time: i64,
    flags: u32,
    minimum_working_set: usize,
    maximum_working_set: usize,
    active_processes: u32,
    affinity: usize,
    priority: u32,
    scheduling: u32,
}
#[repr(C)]
struct IoCounters {
    read_ops: u64,
    write_ops: u64,
    other_ops: u64,
    read_bytes: u64,
    write_bytes: u64,
    other_bytes: u64,
}
#[repr(C)]
struct ExtendedLimits {
    basic: BasicLimits,
    io: IoCounters,
    process_memory: usize,
    job_memory: usize,
    peak_process_memory: usize,
    peak_job_memory: usize,
}
#[repr(C)]
struct ThreadEntry {
    size: u32,
    usage: u32,
    thread_id: u32,
    owner_pid: u32,
    base_priority: i32,
    delta_priority: i32,
    flags: u32,
}
#[link(name = "kernel32")]
unsafe extern "system" {
    fn CreateJobObjectW(attributes: *const c_void, name: *const u16) -> Handle;
    fn SetInformationJobObject(job: Handle, class: i32, info: *const c_void, size: u32) -> i32;
    fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
    fn CloseHandle(handle: Handle) -> i32;
    fn CreateToolhelp32Snapshot(flags: u32, pid: u32) -> Handle;
    fn Thread32First(snapshot: Handle, entry: *mut ThreadEntry) -> i32;
    fn Thread32Next(snapshot: Handle, entry: *mut ThreadEntry) -> i32;
    fn OpenThread(access: u32, inherit: i32, thread_id: u32) -> Handle;
    fn ResumeThread(thread: Handle) -> u32;
}

#[derive(Debug)]
struct OwnedHandle(Handle);
impl Drop for OwnedHandle {
    fn drop(&mut self) {
        // SAFETY: construction below admits only owned, non-null valid handles.
        unsafe {
            CloseHandle(self.0);
        }
    }
}
#[derive(Debug)]
pub(crate) struct ProcessJob(OwnedHandle);
impl ProcessJob {
    pub(crate) fn new() -> io::Result<Self> {
        // SAFETY: null attributes/name request an unnamed, non-inherited job.
        let handle = unsafe { CreateJobObjectW(ptr::null(), ptr::null()) };
        if handle.is_null() {
            return Err(io::Error::last_os_error());
        }
        let job = Self(OwnedHandle(handle));
        // SAFETY: these C-compatible structures contain only integer fields and
        // zero is valid for every field before the explicit kill-on-close flag.
        let mut limits: ExtendedLimits = unsafe { zeroed() };
        limits.basic.flags = 0x00002000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        // SAFETY: valid owned job, correctly sized C structure, synchronous call.
        if unsafe {
            SetInformationJobObject(
                job.0.0,
                9,
                ptr::from_ref(&limits).cast(),
                size_of::<ExtendedLimits>() as u32,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(job)
    }
    pub(crate) fn assign_and_resume(&self, child: &Child) -> io::Result<()> {
        // SAFETY: std Child owns the process handle for this call. The command
        // was created suspended, so no descendant can escape before assignment.
        if unsafe { AssignProcessToJobObject(self.0.0, child.as_raw_handle()) } == 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: documented snapshot flags enumerate threads in the system.
        let snapshot = unsafe { CreateToolhelp32Snapshot(0x00000004, 0) };
        if snapshot == (-1_isize) as Handle {
            return Err(io::Error::last_os_error());
        }
        let snapshot = OwnedHandle(snapshot);
        // SAFETY: integer-only structure; dwSize must be set before enumeration.
        let mut entry: ThreadEntry = unsafe { zeroed() };
        entry.size = size_of::<ThreadEntry>() as u32;
        // SAFETY: valid snapshot and writable, correctly sized entry.
        let mut found = unsafe { Thread32First(snapshot.0, &mut entry) } != 0;
        while found {
            if entry.owner_pid == child.id() {
                // SAFETY: thread id came from the live snapshot; request only
                // suspend/resume access and prohibit inheritance.
                let handle = unsafe { OpenThread(0x0002, 0, entry.thread_id) };
                if handle.is_null() {
                    return Err(io::Error::last_os_error());
                }
                let thread = OwnedHandle(handle);
                // SAFETY: owned thread handle has THREAD_SUSPEND_RESUME access.
                if unsafe { ResumeThread(thread.0) } == u32::MAX {
                    return Err(io::Error::last_os_error());
                }
                return Ok(());
            }
            // SAFETY: same valid snapshot and entry as the initial enumeration.
            found = unsafe { Thread32Next(snapshot.0, &mut entry) } != 0;
        }
        Err(io::Error::other(
            "suspended native hook thread was not found",
        ))
    }
}
