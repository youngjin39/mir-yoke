//! Test-only macOS realtime input; monotonic clocks and all production code stay real.
use std::ffi::{c_int, c_void};
#[repr(C)]
struct Timespec {
    sec: i64,
    nsec: i64,
}
#[repr(C)]
struct Timeval {
    sec: i64,
    usec: i32,
}
unsafe extern "C" {
    fn clock_gettime(clock: c_int, value: *mut Timespec) -> c_int;
    fn gettimeofday(value: *mut Timeval, zone: *mut c_void) -> c_int;
}
unsafe extern "C" fn fixed_clock(clock: c_int, value: *mut Timespec) -> c_int {
    if clock == 0 {
        unsafe {
            *value = Timespec {
                sec: 1_700_000_000,
                nsec: if cfg!(fractional) { 123_456_000 } else { 0 },
            };
        }
        0
    } else {
        unsafe { clock_gettime(clock, value) }
    }
}
unsafe extern "C" fn fixed_time(value: *mut Timeval, _zone: *mut c_void) -> c_int {
    unsafe {
        *value = Timeval {
            sec: 1_700_000_000,
            usec: if cfg!(fractional) { 123_456 } else { 0 },
        };
    }
    0
}
#[repr(C)]
struct Interpose(*const c_void, *const c_void);
// dyld reads these immutable function-address pairs before the test process starts.
unsafe impl Sync for Interpose {}
#[used]
#[unsafe(link_section = "__DATA,__interpose")]
static CLOCK: Interpose = Interpose(fixed_clock as *const c_void, clock_gettime as *const c_void);
#[used]
#[unsafe(link_section = "__DATA,__interpose")]
static TIME: Interpose = Interpose(fixed_time as *const c_void, gettimeofday as *const c_void);
