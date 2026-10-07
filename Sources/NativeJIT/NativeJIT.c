#include "NativeJIT.h"
#include <TargetConditionals.h>
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <errno.h>
#include <mach/mach.h>
#include <pthread.h>
#include <setjmp.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <libkern/OSCacheControl.h>

extern int csops(pid_t, unsigned int, void *, size_t);
extern void *SecTaskCreateFromSelf(CFAllocatorRef);
extern CFTypeRef SecTaskCopyValueForEntitlement(void *, CFStringRef, CFErrorRef *);

bool p7_debugged(void) {
    unsigned int flags = 0;
    return csops(getpid(), 0, &flags, sizeof(flags)) == 0 && (flags & 0x10000000u) != 0;
}
bool p7_get_task_allow(void) {
    void *task = SecTaskCreateFromSelf(NULL);
    if (!task) return false;
    CFTypeRef value = SecTaskCopyValueForEntitlement(task, CFSTR("get-task-allow"), NULL);
    bool allowed = value == kCFBooleanTrue;
    if (value) CFRelease(value);
    CFRelease(task);
    return allowed;
}
int p7_txm_presence(void) {
#if TARGET_OS_IPHONE && !TARGET_OS_SIMULATOR
    void *library = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_LAZY);
    if (!library) return -1;
    uint32_t (*entry)(mach_port_t, const char *) = dlsym(library, "IORegistryEntryFromPath");
    CFTypeRef (*property)(uint32_t, CFStringRef, CFAllocatorRef, uint32_t) = dlsym(library, "IORegistryEntryCreateCFProperty");
    kern_return_t (*release)(uint32_t) = dlsym(library, "IOObjectRelease");
    if (!entry || !property || !release) { dlclose(library); return -1; }
    uint32_t object = entry(0, "IODeviceTree:/chosen/memory-map");
    if (!object) { dlclose(library); return -1; }
    CFTypeRef keys = property(object, CFSTR("IORegistryEntryPropertyKeys"), kCFAllocatorDefault, 0);
    release(object);
    int result = -1;
    if (keys && CFGetTypeID(keys) == CFArrayGetTypeID()) {
        result = CFArrayContainsValue((CFArrayRef)keys, CFRangeMake(0, CFArrayGetCount((CFArrayRef)keys)), CFSTR("TXM")) ? 1 : 0;
    }
    if (keys) CFRelease(keys);
    dlclose(library);
    return result;
#else
    return 0;
#endif
}

struct P7JITPool { void *rx; void *rw; size_t size; size_t used; bool toggle; bool alias; };

#if defined(__arm64__) && TARGET_OS_IPHONE && !TARGET_OS_SIMULATOR
/* StikDebug universal protocol: x16 command, x0/x1 arguments, brk f00d.
 * Executed only after CS_DEBUGGED, on the dedicated JIT preparation queue.
 */
__attribute__((naked, noinline, optnone)) static void *prepare_region(void *address, size_t length) {
    __asm__("mov x16, #1\n brk #0xf00d\n ret");
}
__attribute__((naked, noinline, optnone)) static void detach_script(void) {
    __asm__("mov x16, #0\n brk #0xf00d\n ret");
}
static pthread_mutex_t protocol_lock = PTHREAD_MUTEX_INITIALIZER;
static _Thread_local sigjmp_buf protocol_jump;
static _Thread_local bool protocol_active;
static struct sigaction protocol_previous;
static void trap_handler(int signal) {
    if (protocol_active) siglongjmp(protocol_jump, 1);
    /* Do not longjmp into an uninitialized context on another thread. */
    sigaction(signal, &protocol_previous, NULL);
    raise(signal);
}
static bool prepare_alias(P7JITPool *pool) {
    pthread_mutex_lock(&protocol_lock);
    struct sigaction action = {0};
    action.sa_handler = trap_handler;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTRAP, &action, &protocol_previous) != 0) { pthread_mutex_unlock(&protocol_lock); return false; }
    bool ok = false;
    if (sigsetjmp(protocol_jump, 1) == 0) {
        protocol_active = true;
        void *prepared = prepare_region(pool->rx, pool->size);
        if (prepared == pool->rx) {
            vm_address_t alias = 0;
            vm_prot_t current = 0, maximum = 0;
            kern_return_t result = vm_remap(mach_task_self(), &alias, pool->size, 0, VM_FLAGS_ANYWHERE,
                mach_task_self(), (vm_address_t)pool->rx, false, &current, &maximum, VM_INHERIT_NONE);
            if (result == KERN_SUCCESS) {
                pool->rw = (void *)alias; pool->alias = true;
                if (mprotect(pool->rw, pool->size, PROT_READ | PROT_WRITE) == 0) {
                    detach_script(); ok = true;
                }
            }
        }
    }
    protocol_active = false;
    sigaction(SIGTRAP, &protocol_previous, NULL);
    pthread_mutex_unlock(&protocol_lock);
    return ok;
}
#endif

P7JITPool *p7_jit_create(size_t capacity, int *error) {
    *error = 0;
#if !defined(__arm64__)
    *error = ENOTSUP; return NULL;
#else
    P7JITPool *pool = calloc(1, sizeof(*pool));
    if (!pool) { *error = ENOMEM; return NULL; }
    size_t page = (size_t)getpagesize();
    pool->size = (capacity + page - 1) & ~(page - 1);
    if (!capacity || pool->size < capacity) { free(pool); *error = EINVAL; return NULL; }
#if TARGET_OS_IPHONE && !TARGET_OS_SIMULATOR
    if (!p7_get_task_allow() || !p7_debugged()) { free(pool); *error = EPERM; return NULL; }
    int txm = p7_txm_presence();
    if (txm < 0) { free(pool); *error = ENOTSUP; return NULL; }
    if (txm == 1) {
        pool->rx = mmap(NULL, pool->size, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
        if (pool->rx == MAP_FAILED || !prepare_alias(pool)) {
            *error = EACCES; p7_jit_destroy(pool); return NULL;
        }
        return pool;
    }
#endif
    pool->rx = mmap(NULL, pool->size, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANON | MAP_JIT, -1, 0);
    if (pool->rx == MAP_FAILED) { *error = errno; free(pool); return NULL; }
    pool->rw = pool->rx;
#if TARGET_OS_OSX
    pool->toggle = pthread_jit_write_protect_supported_np();
#endif
    return pool;
#endif
}
void p7_jit_destroy(P7JITPool *pool) {
    if (!pool) return;
    if (pool->alias && pool->rw) vm_deallocate(mach_task_self(), (vm_address_t)pool->rw, pool->size);
    if (pool->rx && pool->rx != MAP_FAILED) munmap(pool->rx, pool->size);
    free(pool);
}
void *p7_jit_emit(P7JITPool *pool, const uint32_t *words, size_t count) {
    if (!pool || !words || count > SIZE_MAX / 4) return NULL;
    size_t size = count * 4, offset = (pool->used + 15) & ~(size_t)15;
    if (offset > pool->size || size > pool->size - offset) return NULL;
#if defined(__arm64__) && TARGET_OS_OSX
    if (pool->toggle) pthread_jit_write_protect_np(0);
#endif
    memcpy((char *)pool->rw + offset, words, size);
    sys_icache_invalidate((char *)pool->rx + offset, size);
#if defined(__arm64__) && TARGET_OS_OSX
    if (pool->toggle) pthread_jit_write_protect_np(1);
#endif
    pool->used = offset + size;
    return (char *)pool->rx + offset;
}
void p7_jit_call(void *code, uint64_t *registers) {
    ((void (*)(uint64_t *))code)(registers);
}
