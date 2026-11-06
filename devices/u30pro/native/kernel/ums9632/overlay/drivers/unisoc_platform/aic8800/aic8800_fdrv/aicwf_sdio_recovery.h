/* SPDX-License-Identifier: GPL-2.0 */
#ifndef AICWF_SDIO_RECOVERY_H
#define AICWF_SDIO_RECOVERY_H
/* Adapted from 33333s/U30pro-openwrt 08bda84b. The caller owns the MMC host.
 * Only the non-destructive flow-credit register is replayed. Data FIFO reads
 * and writes can have committed a prefix before failing: abort/request retune,
 * return the original error, and never duplicate an aggregate or RX prefix. */
#include <linux/atomic.h>
#include <linux/jiffies.h>

static atomic64_t st_bus_errors = ATOMIC64_INIT(0);
static atomic64_t st_read_retry = ATOMIC64_INIT(0), st_read_recovered = ATOMIC64_INIT(0);
static atomic64_t st_bus_failed = ATOMIC64_INIT(0), st_bus_retunes = ATOMIC64_INIT(0);
static atomic64_t st_fifo_failed = ATOMIC64_INIT(0), st_abort_failed = ATOMIC64_INIT(0);

static bool aicwf_sdio_transient(int error)
{
    return error == -EILSEQ || error == -ETIMEDOUT;
}

static void aicwf_sdio_request_retune(struct sdio_func *func)
{
    if (!mmc_card_removed(func->card)) {
        mmc_retune_needed(func->card->host);
        atomic64_inc(&st_bus_retunes);
    }
}

static int aicwf_sdio_read_credit(struct aic_sdio_dev *sdiodev, unsigned int reg, u8 *value)
{
    struct sdio_func *func = sdiodev->func;
    struct mmc_host *host = func->card->host;
    unsigned long deadline = jiffies + msecs_to_jiffies(CMD_TX_TIMEOUT);
    bool was_disabled = host->retune_crc_disable;
    int error = 0, attempt;

    /* Match the MMC API's temporary-disable contract; restore on every exit.
     * Other registers/functions keep the core's original CRC retune policy. */
    sdio_retune_crc_disable(func);
    for (attempt = 0; attempt < 4; attempt++) {
        if (attempt && (time_after_eq(jiffies, deadline) || mmc_card_removed(func->card)))
            break;
        if (attempt) atomic64_inc(&st_read_retry);
        *value = sdio_readb(func, reg, &error);
        if (!error) {
            if (attempt) {
                atomic64_inc(&st_read_recovered);
                if (time_after(jiffies, sdiodev->recovery_since + 10 * HZ)) {
                    sdiodev->recovery_since = jiffies;
                    sdiodev->recovery_burst = 0;
                }
                if (++sdiodev->recovery_burst >= 3) {
                    sdiodev->recovery_burst = 0;
                    aicwf_sdio_request_retune(func);
                }
            }
            break;
        }
        if (!aicwf_sdio_transient(error)) break;
        atomic64_inc(&st_bus_errors);
        if (attempt == 1 || attempt == 3) aicwf_sdio_request_retune(func);
    }
    if (error) atomic64_inc(&st_bus_failed);
    if (!was_disabled) sdio_retune_crc_enable(func);
    return error;
}

static void aicwf_sdio_fifo_error(struct sdio_func *func, int error)
{
    int abort_error;

    if (!aicwf_sdio_transient(error)) return;
    atomic64_inc(&st_bus_errors);
    atomic64_inc(&st_fifo_failed);
    if (mmc_card_removed(func->card)) return;
    /* CRC leaves the function in an interrupted data transfer. Prevent a
     * tuning command before CCCR abort. A timed-out/absent card is not sent an
     * extra blocking command; its original timeout is propagated unchanged. */
    if (error == -EILSEQ) {
        sdio_retune_hold_now(func);
        sdio_f0_writeb(func, func->num, SDIO_CCCR_ABORT, &abort_error);
        sdio_retune_release(func);
        if (abort_error) atomic64_inc(&st_abort_failed);
    }
    aicwf_sdio_request_retune(func);
}

static int aicwf_bus_errors_get(char *buf, const struct kernel_param *kp)
{
    return scnprintf(buf, PAGE_SIZE,
        "errors %lld read_retries %lld read_recovered %lld failed %lld fifo_failed %lld retunes %lld abort_failed %lld\n",
        atomic64_read(&st_bus_errors), atomic64_read(&st_read_retry),
        atomic64_read(&st_read_recovered), atomic64_read(&st_bus_failed),
        atomic64_read(&st_fifo_failed), atomic64_read(&st_bus_retunes), atomic64_read(&st_abort_failed));
}
static const struct kernel_param_ops aicwf_bus_errors_ops = { .get = aicwf_bus_errors_get };
module_param_cb(bus_errors, &aicwf_bus_errors_ops, NULL, 0444);
MODULE_PARM_DESC(bus_errors, "Bounded credit-read retries and non-replayed data FIFO errors");
#endif
