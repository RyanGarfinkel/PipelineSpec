#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define TRACE_DIR "/trace"

static __thread int busy;
static int disabled;

__attribute__((constructor))
static void init(void)
{
	char comm[32] = {0};
	int fd = open("/proc/self/comm", O_RDONLY);

	if(fd >= 0)
	{
		read(fd, comm, sizeof(comm) - 1);
		close(fd);
	}

	disabled = access(TRACE_DIR, F_OK) != 0 || strncmp(comm, "strace", 6) == 0;
}

static void *next(const char *symbol)
{
	int previous = busy;
	busy = 1;
	void *function = dlsym(RTLD_NEXT, symbol);
	busy = previous;
	return function;
}

static void record(const char *name)
{
	char path[64];
	char line[512];

	if(disabled || busy || name == NULL) return;

	busy = 1;
	snprintf(path, sizeof(path), TRACE_DIR "/env.%d", getpid());
	int length = snprintf(line, sizeof(line), "%s\n", name);
	if(length >= (int) sizeof(line)) length = sizeof(line) - 1;

	int fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0644);
	if(fd >= 0)
	{
		write(fd, line, length);
		close(fd);
	}
	busy = 0;
}

char *getenv(const char *name)
{
	static char *(*real)(const char *);

	if(real == NULL) real = next("getenv");
	record(name);
	return real(name);
}

char *secure_getenv(const char *name)
{
	static char *(*real)(const char *);

	if(real == NULL) real = next("secure_getenv");
	record(name);
	return real(name);
}
