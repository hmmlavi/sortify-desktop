/*
 * Sortify native launcher for the portable Windows build.
 *
 * The portable distribution ships the official CPython embeddable runtime
 * (python313.dll) next to this executable, so no Python installation is
 * required.  The launcher behaves like pythonw.exe: it initialises the bundled
 * runtime and runs ``boot.py`` (the startup shim, which runs ``main.py``) from
 * its own directory with no console window.
 *
 * Any failure before Python takes over is reported with a native message box,
 * because a windowed process has no stderr to write to.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define SORTIFY_RUNTIME L"python313.dll"
#define SORTIFY_SCRIPT L"boot.py"

static void sortify_fail(const wchar_t *detail) {
    wchar_t message[1024];
    _snwprintf_s(message, sizeof(message) / sizeof(message[0]), _TRUNCATE,
                 L"Sortify could not start.\n\n%s\n\n"
                 L"If this keeps happening, reinstall Sortify from the original "
                 L"download, or run Sortify.exe --diagnose from a command prompt "
                 L"for details.",
                 detail);
    MessageBoxW(NULL, message, L"Sortify", MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
}

static BOOL sortify_append_utf8(char **argv, int index, const wchar_t *wide) {
    int needed = WideCharToMultiByte(CP_UTF8, 0, wide, -1, NULL, 0, NULL, NULL);
    if (needed <= 0) {
        return FALSE;
    }
    argv[index] = (char *)calloc((size_t)needed, sizeof(char));
    if (argv[index] == NULL) {
        return FALSE;
    }
    return WideCharToMultiByte(CP_UTF8, 0, wide, -1, argv[index], needed, NULL, NULL) > 0;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show_command) {
    wchar_t exe_path[MAX_PATH];
    if (!GetModuleFileNameW(NULL, exe_path, MAX_PATH)) {
        sortify_fail(L"Windows did not report the application location.");
        return 1;
    }
    wchar_t *last_separator = wcsrchr(exe_path, L'\\');
    if (last_separator == NULL) {
        sortify_fail(L"The application path is not a valid Windows path.");
        return 1;
    }
    *last_separator = L'\0';

    /* Run and load relative to the installation folder, never the caller's cwd. */
    if (!SetCurrentDirectoryW(exe_path)) {
        sortify_fail(L"The Sortify installation folder could not be opened.");
        return 1;
    }
    SetDllDirectoryW(exe_path);

    wchar_t script_path[MAX_PATH];
    if (swprintf_s(script_path, MAX_PATH, L"%s\\%s", exe_path, SORTIFY_SCRIPT) < 0 ||
        GetFileAttributesW(script_path) == INVALID_FILE_ATTRIBUTES) {
        sortify_fail(L"The application files are incomplete (boot.py is missing).");
        return 1;
    }

    /* UTF-8 agrees with the UTF-16 argv we pass below, for non-ASCII arguments. */
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONHOME", NULL);

    wchar_t runtime_path[MAX_PATH];
    if (swprintf_s(runtime_path, MAX_PATH, L"%s\\%s", exe_path, SORTIFY_RUNTIME) < 0) {
        sortify_fail(L"The application path is too long.");
        return 1;
    }
    HMODULE runtime = LoadLibraryExW(runtime_path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (runtime == NULL) {
        sortify_fail(L"The bundled Python runtime (python313.dll) is missing.");
        return 1;
    }
    typedef int(__cdecl * sortify_bytes_main)(int, char **);
    sortify_bytes_main run_python =
        (sortify_bytes_main)(void *)GetProcAddress(runtime, "Py_BytesMain");
    if (run_python == NULL) {
        sortify_fail(L"The bundled Python runtime is incomplete.");
        return 1;
    }

    /* Forward user arguments after the script (for example --diagnose). */
    int argc = 0;
    wchar_t **wide_argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (wide_argv == NULL) {
        argc = 0;
    }
    int extra = argc > 1 ? argc - 1 : 0;
    char **argv = (char **)calloc((size_t)extra + 3, sizeof(char *));
    if (argv == NULL) {
        sortify_fail(L"Not enough memory to start Sortify.");
        return 1;
    }
    int count = 0;
    argv[count++] = "Sortify";
    argv[count++] = "boot.py";
    for (int index = 1; index < argc; index++) {
        if (sortify_append_utf8(argv, count, wide_argv[index])) {
            count++;
        }
    }
    LocalFree(wide_argv);

    return run_python(count, argv);
}
