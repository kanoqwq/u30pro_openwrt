/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef U30PRO_PD9_H
#define U30PRO_PD9_H

/* This charger policy is for a battery-backed SGM41513 and a dedicated PD
 * adapter. Data-capable/dual-role partners (including docks) keep stock caps.
 * Select only an advertised 9 V supply; never synthesize a source capability.
 * The native charger prepares its OVP before the caller queues a request.
 */
struct u30pro_pd9_choice {
 unsigned int kind; /* 0: unchanged, 1: fixed, 2: PPS */
 unsigned int ma;
};

/* sprd_charger_manager.c: cm_is_reach_fchg_threshold() and
 * cm_is_disable_fixed_fchg_check(). No SOC percentage or guessed voltage. */
static inline int u30pro_pd9_start_eligible(int ocv, int ibat, int target,
                                         int thermal, unsigned int ocv_max)
{
 return (target >= 1200000 && thermal >= 1000000 &&
         ocv >= 3520000 && ocv < (int)ocv_max) ||
        (ocv >= 3520000 && ibat >= 1200000);
}

static inline int u30pro_pd9_stop_eligible(int vbat, int ibat, int vbus)
{
 return vbat < 3400000 || ibat < 1000000 || vbus < 6500000;
}

static inline struct u30pro_pd9_choice
u30pro_pd9_select(const unsigned int *caps, unsigned int count, int allow_pps)
{
 struct u30pro_pd9_choice fixed = {0, 0}, pps = {0, 0};
 unsigned int i, cap, ma, lo, hi;

 if (!count || count > 7 || (caps[0] >> 30) ||
     ((caps[0] >> 10) & 1023) != 100 ||
     (caps[0] & ((1U << 29) | (1U << 26))))
  return fixed;
 for (i = 1; i < count; i++) {
  cap = caps[i];
  if (!(cap >> 30) && ((cap >> 10) & 1023) == 180) {
   ma = (cap & 1023) * 10;
   if (ma * 9000 <= 15000000U) continue;
   if (ma > 3200) ma = 3200; /* caller applies stock fixed-PD power budget */
   if (ma > fixed.ma) { fixed.kind = 1; fixed.ma = ma; }
  } else if (allow_pps && (cap >> 28) == 12) { /* PPS APDO, not AVS/reserved */
   lo = ((cap >> 8) & 255) * 100;
   hi = ((cap >> 17) & 255) * 100;
   ma = (cap & 127) * 50;
   if (ma * hi <= 15000000U) continue;
   if (ma > 3200) ma = 3200; /* SGM input ceiling; PPS has its own contract */
   if (lo >= 3300 && lo <= 9000 && hi >= 9000 && ma > pps.ma) {
    pps.kind = 2; pps.ma = ma;
   }
  }
 }
 /* Stock fchg_extcon prefers PPS when the adapter offers it. */
 if (pps.ma >= 1000) return pps;
 if (fixed.ma >= 1000) return fixed;
 fixed.kind = fixed.ma = 0;
 return fixed;
}
#endif
