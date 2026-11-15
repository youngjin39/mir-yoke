/* Test-only shared temp-name input. C preserves Apple's variadic open ABI. */
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <string.h>
#include <sys/random.h>
#include <unistd.h>

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
INTERPOSE(entropy, getentropy);
INTERPOSE(collide, open);
