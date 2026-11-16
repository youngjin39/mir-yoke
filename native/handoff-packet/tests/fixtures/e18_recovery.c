/* Test-only syscall inputs, after parent descriptors are pinned; scratch only. */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int collision(const char *path, int flags, ...) {
    static int attempts;
    va_list args;
    va_start(args, flags);
    int mode = (flags & O_CREAT) ? va_arg(args, int) : 0;
    va_end(args);
    if ((flags & O_EXCL) && strstr(path, ".bootstrap-receipt.json.") && attempts++ < 3) {
        errno = EEXIST;
        return -1;
    }
    return open(path, flags, mode);
}
static int liveness(pid_t pid, int signal) {
    const char *mode = getenv("E18_RECOVERY_MODE"), *root = getenv("E18_RECOVERY_ROOT");
    if (mode && root && !strcmp(mode, "receipt-unreadable") && pid == 2147483647) {
        char path[PATH_MAX];
        assert(snprintf(path, sizeof(path), "%s/.mir/bootstrap-receipt.json", root) > 0);
        assert(chmod(path, 0) == 0); /* After provider snapshots; real reader EACCES. */
    }
    return kill(pid == 424243 && signal == 0 ? getpid() : pid, signal);
}
static int publishing;
static int publication(const char *src, const char *dst) {
    const char *mode = getenv("E18_RECOVERY_MODE"), *root = getenv("E18_RECOVERY_ROOT");
    if (mode && root && !strncmp(mode, "publish-", 8) &&
        strstr(dst, "/.mir/bootstrap-receipt.json")) {
        assert(unlink(dst) == 0 && mkdir(dst, 0700) == 0);
        publishing = 1;
        if (!strcmp(mode, "publish-partial")) {
            char directory[PATH_MAX], path[PATH_MAX];
            assert(snprintf(directory, sizeof(directory), "%s/provider-marker", root) > 0);
            assert(mkdir(directory, 0700) == 0);
            assert(snprintf(path, sizeof(path), "%s/retire.txt", directory) > 0);
            FILE *file = fopen(path, "w");
            assert(file && fputs("Both present\n", file) >= 0 && fclose(file) == 0);
        }
    }
    return rename(src, dst); /* Actual EISDIR; rollback follows this syscall. */
}
static int movement(int srcfd, const char *src, int dstfd, const char *dst) {
    const char *root = getenv("E18_RECOVERY_ROOT"), *mode = getenv("E18_RECOVERY_MODE");
    int rollback = publishing && !strcmp(src, "retire.txt");
    if (!root || !mode || (!rollback && strcmp(src, "a.txt") && strcmp(src, "b.txt")))
        return renameat(srcfd, src, dstfd, dst);
    const char *log = getenv("E18_RECOVERY_MOVES");
    FILE *file = fopen(log, "a");
    assert(file && fprintf(file, "%s\n", src) > 0 && fclose(file) == 0);
    if (!strcmp(src, "b.txt") || rollback) {
        if (!strcmp(mode, "move-failure")) {
            assert(unlinkat(srcfd, src, 0) == 0); /* Real renameat ENOENT below. */
        } else if (strstr(mode, "source-swap") || strstr(mode, "parent-swap")) {
            char path[PATH_MAX], held[PATH_MAX], outside[PATH_MAX];
            const char *relative = strstr(mode, "parent-swap") ? "restore" :
                ".mir/slim-quarantine/cccccccccccccccccccccccccccccccc/restore";
            char quarantine[PATH_MAX];
            if (rollback) {
                assert(snprintf(quarantine, sizeof(quarantine),
                    ".mir/slim-quarantine/%s/provider-marker", getenv("E18_TRANSACTION")) > 0);
                relative = strstr(mode, "parent-swap") ? "provider-marker" : quarantine;
            }
            assert(snprintf(path, sizeof(path), "%s/%s", root, relative) > 0);
            assert(snprintf(held, sizeof(held), "%s-held", path) > 0);
            assert(snprintf(outside, sizeof(outside), "%s/../outside", root) > 0);
            assert(rename(path, held) == 0 && symlink(outside, path) == 0);
            /* Both descriptors still bind the original directories. */
        }
    }
    return renameat(srcfd, src, dstfd, dst);
}
static int cleanup(int fd, const char *name, int flags) {
    const char *mode = getenv("E18_RECOVERY_MODE");
    if (mode && ((!strcmp(mode, "cleanup-journal") && !strcmp(name, "slim-transaction.json")) ||
                 (!strcmp(mode, "cleanup-lock") && !strcmp(name, "slim.lock")))) {
        assert(unlinkat(fd, name, 0) == 0 && mkdirat(fd, name, 0700) == 0);
        /* Actual unlinkat EPERM/EISDIR, before durable recovery cleanup completes. */
    }
    return unlinkat(fd, name, flags);
}
#define INTERPOSE(a, b) __attribute__((used, section("__DATA,__interpose"))) \
    static const struct { const void *replacement, *original; } pair_##a = {a, b}
INTERPOSE(liveness, kill);
INTERPOSE(publication, rename);
INTERPOSE(collision, open);
INTERPOSE(movement, renameat);
INTERPOSE(cleanup, unlinkat);
