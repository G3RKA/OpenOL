/* Runs OpenOL's embedded relay (Development/External/openol_relay) as a
   standalone process, exactly as OLGame.exe starts it from "Start Server":
   relay_start(port, "OpenOL", db) + server_run. Used for protocol tests
   without the game. Usage: relay_host.exe [port] [db_path] */
#include <winsock2.h>
#include <ws2tcpip.h>
#include "openol_relay.h"

static Server g_server;

int main(int argc, char **argv) {
    unsigned short port = (unsigned short)(argc > 1 ? atoi(argv[1]) : 7777);
    const char *db = argc > 2 ? argv[2] : "relay_test.db";
    relay_start(&g_server, port, "OpenOL", db);
    printf("relay_host: listening on UDP %u\n", port);
    fflush(stdout);
    server_run(&g_server);
    return 0;
}
