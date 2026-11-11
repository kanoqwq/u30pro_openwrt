/* SPDX-License-Identifier: GPL-2.0 */
#ifndef U30PRO_PMIC_TYPEC_H
#define U30PRO_PMIC_TYPEC_H

/* UMP9651 A001 correction reported and hardware-tested by ly-fv:
 * https://github.com/kanoqwq/u30pro_openwrt/pull/2
 * Silicon identity selects register layout, never a product name or ROM hash.
 * Other revisions keep the firmware's reg property unchanged.
 */
static inline unsigned int
u30pro_pmic_typec_base(unsigned int dt_base, unsigned int low, unsigned int high)
{
 if ((high & 0xffff) == 0x9360 && (low & 0xffff) == 0xb000)
  return 0x300;
 if ((high & 0xffff) == 0x9651 && (low & 0xffff) == 0xa001)
  return 0x380;
 return dt_base;
}
#endif
