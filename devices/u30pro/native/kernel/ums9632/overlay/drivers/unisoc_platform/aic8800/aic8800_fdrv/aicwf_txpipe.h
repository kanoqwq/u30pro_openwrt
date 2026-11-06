/* SPDX-License-Identifier: GPL-2.0 */
/*
 * AIC SDIO aggregate writer. Inspired by 33333s/U30pro-openwrt ff4f4906.
 * One producer (the existing bus TX thread), one writer, three rotating pools.
 * No CPU affinity, frequency votes, polling or runtime backend substitution.
 */
#ifndef AICWF_TXPIPE_H
#define AICWF_TXPIPE_H

#include <linux/err.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/wait.h>

#define AICWF_TXPIPE_POOLS 3
/* Reuse the driver's command deadline instead of an independent short timer. */
#define AICWF_TXPIPE_TIMEOUT_MS CMD_TX_TIMEOUT
#define AICWF_AGGR_MAX 32

struct aicwf_txpipe {
	struct task_struct *task;
	wait_queue_head_t wait;
	spinlock_t lock;
	struct skb_buff_pool *pool[AICWF_TXPIPE_POOLS];
	struct skb_buff_pool extra[AICWF_TXPIPE_POOLS - 1];
	unsigned int fill, write, queued;
	int error;
	bool stopping;
	void *context;
	int (*send)(void *context, struct skb_buff_pool *pool);
};

/* Include final link-tail and CMD53 block padding in every bounds check. */
static bool aicwf_aggr_fits(struct skb_buff_pool *pool, size_t used,
			    size_t append)
{
	size_t capacity;

	if (!pool || !pool->data || !pool->end || pool->end < pool->data)
		return false;
	capacity = min_t(size_t, pool->size, pool->end - pool->data);
	capacity = round_down(capacity, TXPKT_BLOCKSIZE);
	return used <= capacity && append <= capacity - used &&
		TAIL_LEN <= capacity - used - append;
}

static int aicwf_txpipe_error(struct aicwf_txpipe *pipe)
{
	return pipe ? READ_ONCE(pipe->error) : 0;
}

/* queued includes the aggregate currently inside CMD53. */
static bool aicwf_txpipe_busy(struct aicwf_txpipe *pipe)
{
	return pipe && READ_ONCE(pipe->queued);
}

static void aicwf_txpipe_fail(struct aicwf_txpipe *pipe, int error)
{
	unsigned long flags;

	if (!pipe)
		return;
	spin_lock_irqsave(&pipe->lock, flags);
	if (!pipe->error)
		WRITE_ONCE(pipe->error, error);
	spin_unlock_irqrestore(&pipe->lock, flags);
	wake_up_all(&pipe->wait);
}

static void aicwf_txpipe_cancel(struct aicwf_txpipe *pipe)
{
	if (!pipe)
		return;
	WRITE_ONCE(pipe->stopping, true);
	aicwf_txpipe_fail(pipe, -ESHUTDOWN);
}

static int aicwf_txpipe_thread(void *data)
{
	struct aicwf_txpipe *pipe = data;
	struct skb_buff_pool *pool;
	unsigned long flags;
	int ret;

	for (;;) {
		ret = wait_event_interruptible(pipe->wait,
			aicwf_txpipe_busy(pipe) || aicwf_txpipe_error(pipe) ||
			kthread_should_stop());
		if (ret) {
			aicwf_txpipe_fail(pipe, ret);
			break;
		}
		spin_lock_irqsave(&pipe->lock, flags);
		if (pipe->error || pipe->stopping || kthread_should_stop()) {
			spin_unlock_irqrestore(&pipe->lock, flags);
			break;
		}
		pool = pipe->pool[pipe->write];
		spin_unlock_irqrestore(&pipe->lock, flags);
		ret = pipe->send(pipe->context, pool);
		if (ret) {
			aicwf_txpipe_fail(pipe, ret);
			break;
		}
		spin_lock_irqsave(&pipe->lock, flags);
		pipe->write = (pipe->write + 1) % AICWF_TXPIPE_POOLS;
		WRITE_ONCE(pipe->queued, pipe->queued - 1);
		spin_unlock_irqrestore(&pipe->lock, flags);
		wake_up_all(&pipe->wait);
	}
	return 0;
}

/* Called before bus threads start; failure is a probe error, never fallback. */
static struct aicwf_txpipe *aicwf_txpipe_create(struct skb_buff_pool *original,
		void *context, int (*send)(void *, struct skb_buff_pool *))
{
	struct aicwf_txpipe *pipe;
	unsigned int i;
	if (!aicwf_aggr_fits(original, 0, 1600))
		return ERR_PTR(-EINVAL);
	pipe = kzalloc(sizeof(*pipe), GFP_KERNEL);
	if (!pipe)
		return ERR_PTR(-ENOMEM);
	init_waitqueue_head(&pipe->wait);
	spin_lock_init(&pipe->lock);
	pipe->pool[0] = original;
	pipe->context = context;
	pipe->send = send;
	for (i = 1; i < AICWF_TXPIPE_POOLS; i++) {
		struct skb_buff_pool *pool = &pipe->extra[i - 1];

		pool->size = min_t(size_t, original->size,
				  original->end - original->data);
		pool->data = kmalloc(pool->size, GFP_KERNEL);
		if (!pool->data)
			goto fail;
		pool->head = pool->tail = pool->data;
		pool->end = pool->data + pool->size;
		pipe->pool[i] = pool;
	}
	pipe->task = kthread_run(aicwf_txpipe_thread, pipe, "aicwf_sdio_txw");
	if (IS_ERR(pipe->task)) {
		int error = PTR_ERR(pipe->task);

		for (i = 0; i < AICWF_TXPIPE_POOLS - 1; i++)
			kfree(pipe->extra[i].data);
		kfree(pipe);
		return ERR_PTR(error);
	}
	/* The writer can exit on an I/O error before teardown calls stop. */
	get_task_struct(pipe->task);
	return pipe;
fail:
	for (i = 0; i < AICWF_TXPIPE_POOLS - 1; i++)
		kfree(pipe->extra[i].data);
	kfree(pipe);
	return ERR_PTR(-ENOMEM);
}

static int aicwf_txpipe_drain(struct aicwf_txpipe *pipe)
{
	if (!pipe)
		return 0;
	if (!wait_event_timeout(pipe->wait,
		!aicwf_txpipe_busy(pipe) || aicwf_txpipe_error(pipe),
		msecs_to_jiffies(AICWF_TXPIPE_TIMEOUT_MS)))
		aicwf_txpipe_fail(pipe, -ETIMEDOUT);
	return aicwf_txpipe_error(pipe);
}

/* Leave one pool free for the producer, including while a write is in flight. */
static int aicwf_txpipe_submit(struct aicwf_txpipe *pipe)
{
	unsigned long flags;
	int error;

	if (!wait_event_timeout(pipe->wait,
		READ_ONCE(pipe->queued) < AICWF_TXPIPE_POOLS - 1 ||
		aicwf_txpipe_error(pipe),
		msecs_to_jiffies(AICWF_TXPIPE_TIMEOUT_MS)))
		aicwf_txpipe_fail(pipe, -ETIMEDOUT);
	spin_lock_irqsave(&pipe->lock, flags);
	error = pipe->error;
	if (!error) {
		WRITE_ONCE(pipe->queued, pipe->queued + 1);
		pipe->fill = (pipe->fill + 1) % AICWF_TXPIPE_POOLS;
	}
	spin_unlock_irqrestore(&pipe->lock, flags);
	wake_up_all(&pipe->wait);
	return error;
}

/* Before hardware/IRQ teardown, without holding the SDIO host or TX semaphore.
 * The host driver's timeout still governs an already submitted SDIO request.
 * Never free a pool while that request could still reference it.
 */
static void aicwf_txpipe_join(struct aicwf_txpipe *pipe)
{
	if (!pipe || !pipe->task)
		return;
	aicwf_txpipe_cancel(pipe);
	kthread_stop(pipe->task);
	put_task_struct(pipe->task);
	pipe->task = NULL;
}

/* Producer bus thread must also be joined before freeing its current pool. */
static void aicwf_txpipe_destroy(struct aicwf_txpipe *pipe)
{
	unsigned int i;

	if (!pipe)
		return;
	aicwf_txpipe_join(pipe);
	for (i = 0; i < AICWF_TXPIPE_POOLS - 1; i++)
		kfree(pipe->extra[i].data);
	kfree(pipe);
}

#endif
