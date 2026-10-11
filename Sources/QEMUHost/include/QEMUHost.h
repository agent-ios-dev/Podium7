#pragma once
int p7_backend_load(const char *path);
int p7_backend_run(int argc, char **argv);
int p7_backend_stop(void);
const char *p7_backend_error(void);
