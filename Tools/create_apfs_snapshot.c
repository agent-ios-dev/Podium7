/* Research fixture only: create a real APFS snapshot with the host API. */
#include <sys/snapshot.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc != 3 || strncmp(argv[2], "com.apple.os.update-", 20)) {
        fprintf(stderr, "expected explicit fixture mount and official root snapshot name\n");
        return 2;
    }
    int fd = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (fd < 0) { perror("open fixture mount"); return 1; }
    int result = fs_snapshot_create(fd, argv[2], 0);
    int error = errno;
    close(fd);
    if (result) {
        fprintf(stderr, "fs_snapshot_create: %s (%d)\n", strerror(error), error);
        return 1;
    }
    printf("Host APFS snapshot created: %s\n", argv[2]);
    return 0;
}
