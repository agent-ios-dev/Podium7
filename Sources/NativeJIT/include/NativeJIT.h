#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct P7JITPool P7JITPool;
bool p7_debugged(void);
bool p7_get_task_allow(void);
int p7_txm_presence(void); /* -1 unknown, 0 absent, 1 present */
P7JITPool *p7_jit_create(size_t capacity, int *error);
void p7_jit_destroy(P7JITPool *pool);
void *p7_jit_emit(P7JITPool *pool, const uint32_t *words, size_t count);
void p7_jit_call(void *code, uint64_t *registers);
