// SPDX-License-Identifier: GPL-2.0-only
/* Explicit product policy shared by data USB and the Type-C/PD power owner.
 * Battery U30 Pro keeps its original source/boost behavior by default. */
#include <linux/export.h>
#include <linux/moduleparam.h>
#include <linux/sprd_ums9632_product.h>
static bool external_power_only;
core_param(f50pro_external_power_only, external_power_only, bool, 0444);
bool sprd_ums9632_external_power_only(void)
{
	return external_power_only;
}
EXPORT_SYMBOL_GPL(sprd_ums9632_external_power_only);
