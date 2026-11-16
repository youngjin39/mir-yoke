/* Test-only: arm after receipt publication, then provoke real filesystem failures. */
#include <assert.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int armed;
static const char *leaf(const char *path) {
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}
static int publish(const char *src, const char *dst) {
    int result = rename(src, dst);
    const char *root = getenv("E18_JOURNAL_ROOT"), *mode = getenv("E18_JOURNAL_MODE");
    if (result || !root || !mode || strcmp(leaf(dst), "bootstrap-receipt.json"))
        return result;
    char expected[PATH_MAX], journal[PATH_MAX];
    assert(snprintf(expected, sizeof(expected), "%s/.mir/bootstrap-receipt.json", root) > 0);
    assert(!strcmp(dst, expected));
    assert(snprintf(journal, sizeof(journal), "%s/.mir/slim-transaction.json", root) > 0);
    if (!strcmp(mode, "missing")) {
        assert(unlink(journal) == 0);
    } else if (!strcmp(mode, "mismatch") || !strcmp(mode, "unverified") ||
               !strcmp(mode, "status-absent")) {
        const char *id = !strcmp(mode, "mismatch") ? "00000000000000000000000000000000" :
                         getenv("E18_TRANSACTION");
        FILE *file = fopen(journal, "w");
        assert(file && id);
        assert(fprintf(file, "{\"transaction_id\":\"%s\",\"paths\":[\"provider-marker/retire.txt\"]%s}",
                       id, !strcmp(mode, "status-absent") ? "" :
                       !strcmp(mode, "unverified") ? ",\"status\":\"moving\"" :
                       ",\"status\":\"verified\"") > 0);
        assert(fclose(file) == 0);
    }
    armed = 1;
    return result;
}
static int cleanup(int fd, const char *name, int flags) {
    const char *mode = getenv("E18_JOURNAL_MODE"), *root = getenv("E18_JOURNAL_ROOT");
    if (!armed || !mode || !root) return unlinkat(fd, name, flags);
    int journal = !strcmp(name, "slim-transaction.json");
    int lock = !strcmp(name, "slim.lock");
    if ((journal && !strncmp(mode, "journal-", 8)) ||
        (lock && !strncmp(mode, "lock-", 5))) {
        armed = 0;
        assert(unlinkat(fd, name, 0) == 0);
        if (strstr(mode, "directory")) assert(mkdirat(fd, name, 0700) == 0);
        /* Delegate the actual failing unlinkat: EPERM/EISDIR or ENOENT. */
    } else if (journal && !strcmp(mode, "parent-swap")) {
        armed = 0;
        char mir[PATH_MAX], held[PATH_MAX], outside[PATH_MAX];
        assert(snprintf(mir, sizeof(mir), "%s/.mir", root) > 0);
        assert(snprintf(held, sizeof(held), "%s/.mir-held", root) > 0);
        assert(snprintf(outside, sizeof(outside), "%s/../outside", root) > 0);
        assert(rename(mir, held) == 0);
        assert(symlink(outside, mir) == 0);
        /* fd stays bound to .mir-held. Never remove the outside sentinel. */
    }
    return unlinkat(fd, name, flags);
}
#define INTERPOSE(a, b) __attribute__((used, section("__DATA,__interpose"))) \
    static const struct { const void *replacement, *original; } pair_##a = {a, b}
INTERPOSE(publish, rename);
INTERPOSE(cleanup, unlinkat);
