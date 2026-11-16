/* Test-only synthetic pid and temp input; all mutations stay in caller scratch. */
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <string.h>
#include <sys/random.h>
#include <unistd.h>

static pid_t fixed_pid(void) {
    Dl_info caller;
    if (dladdr(__builtin_return_address(0), &caller)) {
        const char *base = strrchr(caller.dli_fname, '/');
        if (base && (!strcmp(base, "/mir") || !strcmp(base, "/Python")))
            return 424242;
    }
    return getpid();
}
static int entropy(void *buf, size_t len) {
    if (len != 8) return getentropy(buf, len);
    memset(buf, 0, len);
    return 0;
}
static int collide(const char *path, int flags, ...) {
    static _Atomic int attempts;
    va_list args;
    va_start(args, flags);
    int mode = (flags & O_CREAT) ? va_arg(args, int) : 0;
    va_end(args);
    if ((flags & O_EXCL) && strstr(path, ".memory.bootstrap.") &&
        atomic_fetch_add(&attempts, 1) < 3) {
        errno = EEXIST;
        return -1;
    }
    return open(path, flags, mode);
}
#define INTERPOSE(a, b) __attribute__((used, section("__DATA,__interpose"))) \
    static const struct { const void *replacement, *original; } pair_##a = {a, b}
INTERPOSE(fixed_pid, getpid);
INTERPOSE(entropy, getentropy);
INTERPOSE(collide, open);
