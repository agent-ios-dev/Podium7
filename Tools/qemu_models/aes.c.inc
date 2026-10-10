/* T8010 AES-v2 research engine: software keys and direct physical RAM DMA.
 * Command protocol reference: checkra1n/PongoOS src/drivers/aes/aes_a9.c
 * and TrungNguyen1909/qemu-t8030 at fd4b0f790903044d90b8a35fcf03758401252063.
 * Implementation GPL-2.0-or-later. No hardware UID/GID or wrapped-key support.
 * No DART/SART translation or hardware timing. DPA seed is research boot state.
 */
#include "crypto/cipher.h"
#include "crypto/random.h"
#include "exec/address-spaces.h"
#include "qemu/bswap.h"
typedef struct Podium7AES {
    MemoryRegion io;
    uint64_t base, ram_size;
    uint32_t registers[0x1000];
    unsigned logged_accesses;
    uint8_t dpa_seed[32], key[2][32], iv[4][16];
    unsigned key_bytes[2], mode[2];
    bool encrypt[2], started;
    uint32_t packet[9];
    unsigned packet_words, packet_read;
} Podium7AES;
static void podium7_aes_irq(Podium7AES *s)
{
    if (s->base == 0x20a108000ULL) {
        podium7_aic_set_external(237, (s->registers[6] & s->registers[7]) != 0);
    }
}
static void podium7_aes_error(Podium7AES *s, uint32_t status)
{
    s->registers[6] |= status;
    podium7_aes_irq(s);
}
static bool podium7_aes_dma_range(Podium7AES *s, uint64_t address, unsigned length)
{
    return address >= 0x40000000ULL && address < 0x40000000ULL + s->ram_size &&
           length <= 0x40000000ULL + s->ram_size - address;
}
static void podium7_aes_packet(Podium7AES *s)
{
    uint32_t command = s->packet[0];
    unsigned operation = command >> 28, ctx = (command >> 27) & 1;
    if (operation == 1) {
        unsigned bits = (command >> 22) & 3;
        s->key_bytes[ctx] = 0;
        if (((command >> 24) & 7) || (command & (1U << 21))) {
            podium7_aes_error(s, 1U << (ctx ? 13 : 7));
            return;
        }
        if (bits > 2 || ((command >> 16) & 3) > 1) {
            podium7_aes_error(s, 1U << 2);
            return;
        }
        s->key_bytes[ctx] = 16 + bits * 8;
        for (unsigned i = 0; i < s->key_bytes[ctx] / 4; i++) {
            stl_le_p(s->key[ctx] + i * 4, s->packet[i + 1]);
        }
        s->mode[ctx] = (command >> 16) & 3;
        s->encrypt[ctx] = (command & (1U << 20)) != 0;
        s->registers[4] = (s->registers[4] & ~(0xffU << (ctx * 8))) |
                          ((command & 0xff) << (ctx * 8));
    } else if (operation == 2) {
        unsigned iv_ctx = (command >> 26) & 3;
        for (unsigned i = 0; i < 4; i++) {
            stl_le_p(s->iv[iv_ctx] + i * 4, s->packet[i + 1]);
        }
    } else if (operation == 5) {
        unsigned length = command & 0xffffff, iv_ctx = (command >> 25) & 3;
        uint64_t source = ((uint64_t)((s->packet[1] >> 16) & 0xff) << 32) | s->packet[2];
        uint64_t target = ((uint64_t)(s->packet[1] & 0xff) << 32) | s->packet[3];
        if (!length || (length & 15)) { podium7_aes_error(s, 1U << 6); return; }
        if (!s->key_bytes[ctx]) { podium7_aes_error(s, 1U << (ctx ? 13 : 7)); return; }
        if (!podium7_aes_dma_range(s, source, length) || !podium7_aes_dma_range(s, target, length)) {
            podium7_aes_error(s, (1U << 3) | (1U << 4)); return;
        }
        QCryptoCipherAlgo algorithm = s->key_bytes[ctx] == 16 ? QCRYPTO_CIPHER_ALGO_AES_128 :
            s->key_bytes[ctx] == 24 ? QCRYPTO_CIPHER_ALGO_AES_192 : QCRYPTO_CIPHER_ALGO_AES_256;
        Error *error = NULL;
        QCryptoCipher *cipher = qcrypto_cipher_new(algorithm,
            s->mode[ctx] ? QCRYPTO_CIPHER_MODE_CBC : QCRYPTO_CIPHER_MODE_ECB,
            s->key[ctx], s->key_bytes[ctx], &error);
        uint8_t *data = g_malloc(length);
        bool ok = cipher != NULL;
        if (ok) { ok = address_space_read(&address_space_memory, source, MEMTXATTRS_UNSPECIFIED, data, length) == MEMTX_OK; }
        if (ok && s->mode[ctx]) { ok = qcrypto_cipher_setiv(cipher, s->iv[iv_ctx], 16, &error) == 0; }
        uint8_t next_iv[16];
        if (ok && s->mode[ctx] && !s->encrypt[ctx]) { memcpy(next_iv, data + length - 16, 16); }
        if (ok) { ok = (s->encrypt[ctx] ? qcrypto_cipher_encrypt(cipher, data, data, length, &error) :
                                          qcrypto_cipher_decrypt(cipher, data, data, length, &error)) == 0; }
        if (ok && s->mode[ctx]) {
            if (s->encrypt[ctx]) { memcpy(next_iv, data + length - 16, 16); }
            memcpy(s->iv[iv_ctx], next_iv, 16);
        }
        if (ok) { ok = address_space_write(&address_space_memory, target, MEMTXATTRS_UNSPECIFIED, data, length) == MEMTX_OK; }
        if (!ok) { podium7_aes_error(s, (1U << 3) | (1U << 4)); }
        else { qemu_log("PODIUM7 AES crypto completed bytes=%u context=%u mode=%u encrypt=%u\n",
                        length, ctx, s->mode[ctx], s->encrypt[ctx]); }
        if (cipher) { qcrypto_cipher_free(cipher); }
        if (error) { error_free(error); }
        g_free(data);
    } else if (operation == 6) {
        unsigned iv_ctx = (command >> 26) & 3;
        uint64_t target = ((uint64_t)(command & 0xff) << 32) | s->packet[1];
        if (!podium7_aes_dma_range(s, target, 16) ||
            address_space_write(&address_space_memory, target, MEMTXATTRS_UNSPECIFIED,
                                s->iv[iv_ctx], 16) != MEMTX_OK) {
            podium7_aes_error(s, 1U << 4);
        }
    } else if (operation == 8) {
        s->registers[0x30 >> 2] = command & 0xffff;
        if (command & (1U << 27)) { s->registers[6] |= 1U << 5; }
        if (command & (1U << 26)) { s->started = false; }
        podium7_aes_irq(s);
    } else { podium7_aes_error(s, 1U << 2); }
}
static uint64_t podium7_aes_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7AES *s = opaque;
    uint32_t value = s->registers[address >> 2];
    if (s->base == 0x2102d0000ULL) { value = 0xff; /* All unknown platform keys disabled. */ }
    else if (address == 0xc) { value = 0x180 | (s->started ? 1U << 6 : 0); }
    else if (address == 0x24) { value = 3; /* Synchronous engine has no queued commands. */ }
    if (s->logged_accesses++ < 256) {
        qemu_log("PODIUM7 AES base=%016" PRIx64 " read offset=%04" PRIx64 " value=%08" PRIx32 "\n",
                 s->base, (uint64_t)address, value);
    }
    return value;
}
static void podium7_aes_write(void *opaque, hwaddr address, uint64_t data, unsigned size)
{
    Podium7AES *s = opaque;
    uint32_t value = data;
    if (s->base == 0x2102d0000ULL) { return; }
    if (address == 0x18) { s->registers[6] &= ~value; podium7_aes_irq(s); }
    else if (address == 0x1c) { s->registers[7] = value; podium7_aes_irq(s); }
    else if (address == 8) {
        if (value & 0xc) { s->packet_words = s->packet_read = 0; s->started = false; }
        if (value & 8) { memset(s->key_bytes, 0, sizeof(s->key_bytes)); }
        if (value & 1) { s->started = true; }
        if (value & 2) { s->started = false; }
    } else if (address == 0x200) {
        if (!s->started) { podium7_aes_error(s, 1U << 2); return; }
        if (!s->packet_words) {
            unsigned op = value >> 28;
            s->packet_words = op == 1 ? (((value >> 24) & 7) ? 1 : (5 + 2 * ((value >> 22) & 3))) :
                              op == 2 ? 5 : op == 5 ? 4 : op == 6 ? 2 : op == 8 ? 1 : 0;
            if (!s->packet_words || s->packet_words > ARRAY_SIZE(s->packet)) {
                s->packet_words = 0; podium7_aes_error(s, 1U << 2); return;
            }
        }
        s->packet[s->packet_read++] = value;
        if (s->packet_read == s->packet_words) {
            podium7_aes_packet(s);
            s->packet_words = s->packet_read = 0;
            s->registers[0x2c >> 2]++;
        }
    } else if (address != 0xc && address != 0x10 && address != 0x24 && address != 0x2c && address != 0x30) {
        s->registers[address >> 2] = value;
    }
    if (s->logged_accesses++ < 256) {
        qemu_log("PODIUM7 AES base=%016" PRIx64 " write offset=%04" PRIx64 " value=%08" PRIx32 "\n",
                 s->base, (uint64_t)address, value);
    }
}
static const MemoryRegionOps podium7_aes_ops = {
    .read = podium7_aes_read, .write = podium7_aes_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
};
static void podium7_aes_create(MachineState *machine, MemoryRegion *memory, hwaddr base, const char *name)
{
    Podium7AES *s = g_new0(Podium7AES, 1);
    s->base = base; s->ram_size = machine->ram_size;
    qcrypto_random_bytes(s->dpa_seed, sizeof(s->dpa_seed), &error_fatal);
    memory_region_init_io(&s->io, OBJECT(machine), &podium7_aes_ops, s, name, 0x4000);
    memory_region_add_subregion(memory, base, &s->io);
}
