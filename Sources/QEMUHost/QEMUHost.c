#include "QEMUHost.h"
#include <dlfcn.h>
#include <stdio.h>
#include <pthread.h>

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static void *image;
static int (*run_backend)(int, char **);
static int (*stop_backend)(void);
static char error[256];
static int used;

int p7_backend_load(const char *path) {
    pthread_mutex_lock(&lock);
    if (image) { pthread_mutex_unlock(&lock); return 0; }
    image = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!image) {
        snprintf(error, sizeof(error), "%s", dlerror());
        pthread_mutex_unlock(&lock); return -1;
    }
    int (*abi)(void) = (int (*)(void))dlsym(image, "p7_qemu_abi");
    run_backend = (int (*)(int, char **))dlsym(image, "p7_qemu_run");
    stop_backend = (int (*)(void))dlsym(image, "p7_qemu_stop");
    if (!abi || !run_backend || !stop_backend || abi() != 1) {
        snprintf(error, sizeof(error), "Unsupported QEMU framework ABI");
        dlclose(image); image = NULL; run_backend = NULL; stop_backend = NULL;
        pthread_mutex_unlock(&lock); return -2;
    }
    /* Never unload an initialized QEMU: threads and global state remain live. */
    pthread_mutex_unlock(&lock); return 0;
}

int p7_backend_run(int argc, char **argv) {
    pthread_mutex_lock(&lock);
    if (!run_backend || used) { pthread_mutex_unlock(&lock); return -2; }
    used = 1;
    pthread_mutex_unlock(&lock);
    return run_backend(argc, argv);
}

const char *p7_backend_error(void) { return error; }

int p7_backend_stop(void) {
    pthread_mutex_lock(&lock);
    int (*stop)(void) = stop_backend;
    pthread_mutex_unlock(&lock);
    return stop ? stop() : -1;
}
