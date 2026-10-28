/* Host test of the v7 enemy-animation code: olfix.c is compiled into this program with a fake game image (OLFIX_HOST_TEST) and mocks of the engine
   functions it calls by RVA. Nothing of the game is needed. It checks the packet the owner builds, how the puppet side parses and queues it, and the
   arguments of the script call (FName strings, parameter block, the immediates of L"PlayFullBodyAnim").
     python -I hosttest.py          builds and runs it (needs MinGW gcc) */
#define OLFIX_HOST_TEST 1
#include "olfix.c"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define IMAGE_SIZE 0x3A00000
static char *g_ib;
char *test_ib(void) { return g_ib; }

static int fails;
#define CHECK(c, ...) do { if (c) printf("PASS %s\n", #c); else { fails++; printf("FAIL %s  ", #c); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* ---- mocks of engine functions (ms_abi like the real ones) ---- */
static unsigned char sent[512]; static int sent_n, sent_count;
static void mock_SendBinary(void *conn, const char *buf, i32 n) { (void)conn; memcpy(sent, buf, n); sent_n = n; sent_count++; }
static void mock_AppFree(void *p) { free(p); }
static void *mock_FString(const char *ascii, struct fstr *out)
{
    int n = (int)strlen(ascii);
    out->data = malloc((n + 1) * 2);
    for (int i = 0; i <= n; i++) out->data[i] = (unsigned char)ascii[i];
    out->num = n + 1; out->max = n + 1;
    return out;
}
static const char *g_enemy_name = "OLEnemyPatient_3";
static const char *g_anim_name = "Idle_LeanWall";
static void *mock_GetName(void *obj, void *out) { (void)obj; return mock_FString(g_enemy_name, (struct fstr *)out); }
static void *mock_ToString(void *fname, void *out) { (void)fname; return mock_FString(g_anim_name, (struct fstr *)out); }
static char last_ctor[8][80]; static int ctor_n;
static void mock_NameCtor(u32 *fn, const unsigned short *w, i32 find)
{
    char s[80]; int i = 0;
    for (; w[i] && i < 79; i++) s[i] = (char)w[i];
    s[i] = 0;
    strcpy(last_ctor[ctor_n++ & 7], s);
    unsigned h = 5381; for (const char *p = s; *p; p++) h = h * 33 + (unsigned char)*p;
    fn[0] = h; fn[1] = 0; (void)find;
}
static unsigned hash_of(const char *s) { unsigned h = 5381; for (; *s; s++) h = h * 33 + (unsigned char)*s; return h; }
static char *g_func = (char *)0x1234567;
static char *mock_FindFunc(char *obj, unsigned long long fname) { (void)obj; return (unsigned)fname == hash_of("PlayFullBodyAnim") ? g_func : 0; }
static u32 pe_parm[8]; static int pe_calls; static char *pe_obj, *pe_func;
static void mock_ProcessEvent(char *obj, char *func, void *parms, void *res) { (void)res; pe_obj = obj; pe_func = func; memcpy(pe_parm, parms, 32); pe_calls++; }
static i32 mock_Tick(char *pc, float dt, i32 t) { (void)pc; (void)dt; (void)t; return 1; }
static int send_spawn_calls;
static void mock_SendSpawn(char *ch, char *e) { (void)ch; (void)e; send_spawn_calls++; }
static int destroyed_n; static char *destroyed_actor;
static i32 mock_DestroyActor(void *world, char *actor, i32 a, i32 b) { (void)world; (void)a; (void)b; destroyed_actor = actor; destroyed_n++; return 1; }
static void *mock_AppRealloc(void *old, u32 bytes, u32 align) { (void)align; return realloc(old, bytes); }
static int addsets_calls, addsets_n; static char *addsets_to; static void *addsets_first;
static void mock_AddAnimSets(char *pawn, char *tarray) { addsets_calls++; addsets_to = pawn; addsets_n = *(i32 *)(tarray + 8); addsets_first = **(void ***)tarray; }

static void tramp(unsigned rva, void *fn)       /* mov rax, imm64 ; jmp rax at ib + rva */
{
    unsigned char *p = (unsigned char *)(g_ib + rva);
    p[0] = 0x48; p[1] = 0xB8; memcpy(p + 2, &fn, 8); p[10] = 0xFF; p[11] = 0xE0;
}

int main(void)
{
    g_ib = VirtualAlloc(0, IMAGE_SIZE, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!g_ib) { puts("cannot allocate the fake image"); return 2; }
    tramp(RVA_SENDBINARY, mock_SendBinary); tramp(RVA_APPFREE, mock_AppFree); tramp(RVA_GETNAME, mock_GetName);
    tramp(RVA_NAME_TOSTRING, mock_ToString); tramp(RVA_NAME_CTOR, mock_NameCtor); tramp(RVA_FINDFUNC, mock_FindFunc);
    tramp(RVA_TICK, mock_Tick); tramp(RVA_DESTROYACTOR, mock_DestroyActor); tramp(RVA_APPREALLOC, mock_AppRealloc);
    *(i32 *)(g_ib + RVA_SYNCENEMIES) = 1;
    *(i32 *)(g_ib + RVA_LOCALPLAYERID) = 2;
    *(i32 *)(g_ib + RVA_GMPCONN + 0x30) = 1;
    *(i32 *)(g_ib + RVA_GMPCONN + 0x34) = 1;

    /* a channel, its controller and a vtable whose slot +0x268 is the original SendSpawn */
    static char ch[0x400], ctrl[0x1400], vt[0x400], pawn[0x3000], bot[0x800], dummy[0x3000], dvt[0x400], remote[0x44 * 2];
    *(char **)ch = vt; *(char **)(ch + CH_CONTROLLER) = ctrl;
    *(void **)(vt + 0x268) = (void *)mock_SendSpawn;
    *(void **)(dvt + VT_PROCESSEVENT) = (void *)mock_ProcessEvent;
    *(char **)(pawn + OBJ_CLASS) = (char *)0x7000; *(i32 *)(pawn + PAWN_HEALTH) = 100;
    *(char **)(pawn + PAWN_BOT) = bot;
    *(u32 *)(bot + BOT_CURANIM) = 4242; *(u32 *)(bot + BOT_CURANIM + 4) = 0;
    *(u32 *)(bot + BOT_CURANIM + 8) = 1;                                    /* loop */
    float f[5] = {1.0f, 0.2f, 0.25f, 0.0f, 0.0f};
    memcpy(bot + BOT_CURANIM + 12, f, 20);

    volatile u32 *d = data_area(g_ib);

    /* ---- owner side ---- */
    my_SendSpawn(ch, pawn);                                                 /* no animation: nothing sent, original SendSpawn called */
    CHECK(sent_count == 0 && send_spawn_calls == 1, "sent %d, original calls %d", sent_count, send_spawn_calls);
    *(u32 *)(bot + BOT_FLAGS) = 0x4000;                                     /* bAnimating but the script has not started the animation yet */
    my_SendSpawn(ch, pawn);
    CHECK(sent_count == 0, "sent %d before bIsAnimatingFullBody", sent_count);
    *(u32 *)(pawn + PAWN_FLAGS) = 0x10;
    my_SendSpawn(ch, pawn);
    CHECK(sent_count == 1 && d[F_CNT_ANIM_SENT / 4] == 1, "sent %d, counter %u", sent_count, d[F_CNT_ANIM_SENT / 4]);
    unsigned char want[160]; int k = 0;
    want[k++] = 5; want[k++] = 0x12; want[k++] = 16; memcpy(want + k, "OLEnemyPatient_3", 16); k += 16;
    want[k++] = 13; memcpy(want + k, "Idle_LeanWall", 13); k += 13;
    want[k++] = 1; memcpy(want + k, f, 20); k += 20;
    CHECK(sent_n == k && memcmp(sent, want, k) == 0, "packet length %d (want %d)", sent_n, k);
    unsigned char first[512]; int first_n = sent_n; memcpy(first, sent, sent_n);
    my_SendSpawn(ch, pawn);
    CHECK(sent_count == 1, "the same animation was announced again (%d)", sent_count);
    int again = 0;
    for (int i = 0; i < ANIM_REFRESH_CALLS + 2; i++) my_SendSpawn(ch, pawn);
    again = sent_count;
    CHECK(again == 2 && (sent[2 + 1 + 16 + 1 + 13] & 2) == 2, "after %d ticks: %d packets, flags byte %02x", ANIM_REFRESH_CALLS, again, sent[2 + 1 + 16 + 1 + 13]);
    *(u32 *)(bot + BOT_FLAGS) = 0;                                          /* the animation ended ... */
    my_SendSpawn(ch, pawn);
    *(u32 *)(bot + BOT_FLAGS) = 0x4000;                                     /* ... and the next episode is announced again */
    my_SendSpawn(ch, pawn);
    CHECK(sent_count == 3 && (sent[2 + 1 + 16 + 1 + 13] & 2) == 0, "after a new episode: %d packets", sent_count);
    d[F_DISABLE / 4] = DISABLE_ANIM;
    *(u32 *)(bot + BOT_FLAGS) = 0; my_SendSpawn(ch, pawn); *(u32 *)(bot + BOT_FLAGS) = 0x4000;
    my_SendSpawn(ch, pawn);
    CHECK(sent_count == 3, "the kill switch did not stop the sender (%d)", sent_count);
    d[F_DISABLE / 4] = 0;

    /* ---- puppet side: a remote enemy record of player 1 ---- */
    static unsigned short wname[32];
    for (int i = 0; i <= 16; i++) wname[i] = (unsigned char)"OLEnemyPatient_3"[i];
    *(unsigned short **)remote = wname; *(i32 *)(remote + 8) = 17; *(i32 *)(remote + 12) = 17;
    *(char **)(remote + REMOTE_DUMMY) = dummy; *(i32 *)(remote + REMOTE_OWNER) = 1;
    *(char **)(ctrl + CTRL_REMOTE) = remote; *(i32 *)(ctrl + CTRL_REMOTE + 8) = 1;
    *(char **)dummy = dvt; *(i32 *)(dummy + PAWN_HEALTH) = 100; *(char **)(dummy + PAWN_SLOT) = (char *)0x5000;
    CHECK(*(char *volatile *)((volatile char *)d + F_LAST_CTRL) == ctrl, "last_ctrl not recorded");

    my_WorldPacket(ch, 1, 0x12, first + 2, first_n - 2);
    CHECK(d[F_CNT_ANIM_RECV / 4] == 1, "recv counter %u", d[F_CNT_ANIM_RECV / 4]);
    CHECK(my_Tick(ctrl, 0.016f, 0) == 1 && pe_calls == 1, "script calls: %d", pe_calls);
    CHECK(pe_obj == dummy && pe_func == g_func, "called on %p function %p", (void *)pe_obj, (void *)pe_func);
    CHECK(pe_parm[0] == hash_of("Idle_LeanWall") && pe_parm[1] == 0, "anim FName %u/%u", pe_parm[0], pe_parm[1]);
    CHECK(pe_parm[2] == *(u32 *)&f[0] && pe_parm[3] == *(u32 *)&f[1] && pe_parm[4] == *(u32 *)&f[2], "rate/blend bits %08x %08x %08x", pe_parm[2], pe_parm[3], pe_parm[4]);
    CHECK(pe_parm[5] == 1 && pe_parm[6] == 0 && pe_parm[7] == 0, "loop/start/end %u %u %u", pe_parm[5], pe_parm[6], pe_parm[7]);
    CHECK(strcmp(last_ctor[(ctor_n - 2) & 7], "Idle_LeanWall") == 0 && strcmp(last_ctor[(ctor_n - 1) & 7], "PlayFullBodyAnim") == 0,
          "FName strings '%s' '%s'", last_ctor[(ctor_n - 2) & 7], last_ctor[(ctor_n - 1) & 7]);
    CHECK(d[F_CNT_ANIM_PLAYED / 4] == 1 && d[F_CNT_ANIM_DROPPED / 4] == 0, "played %u dropped %u", d[F_CNT_ANIM_PLAYED / 4], d[F_CNT_ANIM_DROPPED / 4]);

    my_Tick(ctrl, 0.016f, 0);                                               /* the queue entry was consumed */
    CHECK(pe_calls == 1, "played twice (%d)", pe_calls);

    /* a refresh while the puppet already animates is skipped; without the full-body flag it plays */
    unsigned char refresh[512]; memcpy(refresh, first, first_n); refresh[2 + 1 + 16 + 1 + 13] = 3;
    *(u32 *)(dummy + PAWN_FLAGS) = 0x10;
    my_WorldPacket(ch, 1, 0x12, refresh + 2, first_n - 2); my_Tick(ctrl, 0.016f, 0);
    CHECK(pe_calls == 1, "refresh restarted a running animation (%d)", pe_calls);
    *(u32 *)(dummy + PAWN_FLAGS) = 0;
    my_WorldPacket(ch, 1, 0x12, refresh + 2, first_n - 2); my_Tick(ctrl, 0.016f, 0);
    CHECK(pe_calls == 2, "refresh did not play on an idle puppet (%d)", pe_calls);

    /* drops: another sender, an unknown enemy, a dead puppet, a puppet without slot, a short packet */
    u32 dropped = d[F_CNT_ANIM_DROPPED / 4];
    my_WorldPacket(ch, 7, 0x12, first + 2, first_n - 2); my_Tick(ctrl, 0.016f, 0);
    *(i32 *)(dummy + PAWN_HEALTH) = 0;
    my_WorldPacket(ch, 1, 0x12, first + 2, first_n - 2); my_Tick(ctrl, 0.016f, 0);
    *(i32 *)(dummy + PAWN_HEALTH) = 100; *(char **)(dummy + PAWN_SLOT) = 0;
    my_WorldPacket(ch, 1, 0x12, first + 2, first_n - 2); my_Tick(ctrl, 0.016f, 0);
    *(char **)(dummy + PAWN_SLOT) = (char *)0x5000;
    CHECK(pe_calls == 2 && d[F_CNT_ANIM_DROPPED / 4] == dropped + 3, "calls %d, dropped %u (was %u)", pe_calls, d[F_CNT_ANIM_DROPPED / 4], dropped);
    my_WorldPacket(ch, 1, 0x12, first + 2, 5); my_Tick(ctrl, 0.016f, 0);
    CHECK(pe_calls == 2, "a truncated packet played");
    d[F_DISABLE / 4] = DISABLE_ANIM;
    my_WorldPacket(ch, 1, 0x12, first + 2, first_n - 2); my_Tick(ctrl, 0.016f, 0);
    CHECK(pe_calls == 2, "the kill switch did not stop the receiver");
    d[F_DISABLE / 4] = 0;
    my_Tick((char *)0x9999, 0.016f, 0);                                     /* a queued entry is played only by the controller the hooks saw */
    my_WorldPacket(ch, 1, 0x12, first + 2, first_n - 2); my_Tick((char *)0x9999, 0.016f, 0);
    CHECK(pe_calls == 2, "another controller played the queue");
    my_Tick(ctrl, 0.016f, 0);
    CHECK(pe_calls == 3, "the queued entry was lost (%d)", pe_calls);

    /* ---- the merge hands the animation sets of the dropped own copy to the puppet ---- */
    static void *sets[2] = {(void *)0xA1, (void *)0xA2};
    *(void ***)(pawn + PAWN_SPAWNER_SETS) = sets; *(i32 *)(pawn + PAWN_SPAWNER_SETS + 8) = 2; *(i32 *)(pawn + PAWN_SPAWNER_SETS + 12) = 2;
    *(void **)(dvt + VT_ADDANIMSETS) = (void *)mock_AddAnimSets;
    *(char **)(dummy + OBJ_CLASS) = (char *)0x7000;
    int spawns = send_spawn_calls, destroyed = destroyed_n;
    my_SendSpawn(ch, pawn);                                                 /* a lower id owns this enemy: ours is dropped, the puppet stays */
    CHECK(destroyed_n == destroyed + 1 && destroyed_actor == pawn && send_spawn_calls == spawns, "destroyed %d actor %p, original SendSpawn calls %d", destroyed_n - destroyed, (void *)destroyed_actor, send_spawn_calls - spawns);
    CHECK(addsets_calls == 1 && addsets_to == dummy && addsets_n == 2 && addsets_first == sets[0], "AddAnimSets calls %d, num %d", addsets_calls, addsets_n);
    void **mine = *(void ***)(dummy + PAWN_SPAWNER_SETS);
    CHECK(mine && mine != sets && mine[0] == sets[0] && mine[1] == sets[1] && *(i32 *)(dummy + PAWN_SPAWNER_SETS + 8) == 2, "the puppet's own list was not filled");

    printf("%s\n", fails ? "HOSTTEST FAIL" : "HOSTTEST OK");
    return fails ? 1 : 0;
}
