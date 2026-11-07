/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef U30PRO_BATTERY_PROFILE_H
#define U30PRO_BATTERY_PROFILE_H

#include <linux/err.h>
#include <linux/kernel.h>
#include <linux/kstrtox.h>
#include <linux/of.h>
#include <linux/string.h>

/* Stock resistor-ID selection shared by the charger and FGU. The caller owns
 * the returned OF reference. Never substitute the first global battery node.
 */
static inline struct device_node *
u30pro_battery_profile(struct device_node *owner, int *index, int *id_mv)
{
	struct device_node *chosen, *first, *battery;
	const char *cmdline, *id;
	char text[16], name[32];
	u32 pullup = 475, ref = 1850, target;
	int i, len, ret, mv, resistance, count, match = -1;

	chosen = of_find_node_by_path("/chosen");
	if (!chosen)
		return ERR_PTR(-EINVAL);
	ret = of_property_read_string(chosen, "bootargs", &cmdline);
	of_node_put(chosen);
	if (ret)
		return ERR_PTR(ret);
	id = cmdline;
	while ((id = strstr(id, "bat.id="))) {
		if (id == cmdline || id[-1] == ' ')
			break;
		id++;
	}
	if (!id)
		return ERR_PTR(-ENODATA);
	id += strlen("bat.id=");
	len = strcspn(id, " \n\t");
	if (!len || len >= sizeof(text))
		return ERR_PTR(-EINVAL);
	memcpy(text, id, len);
	text[len] = 0;
	ret = kstrtoint(text, 10, &mv);
	if (ret)
		return ERR_PTR(ret);
	first = of_parse_phandle(owner, "monitored-battery-0", 0);
	if (!first)
		return ERR_PTR(-EINVAL);
	of_property_read_u32(first, "batt-id-pullup-kohm", &pullup);
	of_property_read_u32(first, "batt-id-ref-vol", &ref);
	if (!ref || ref > 5000 || !pullup || pullup > 10000 || mv < 0 || mv >= ref) {
		ret = -EINVAL;
		goto put_first;
	}
	resistance = DIV_ROUND_CLOSEST(mv * pullup, ref - mv);
	count = of_property_count_u32_elems(first, "batt-id-list");
	if (count <= 0 || count > 16) {
		ret = -EINVAL;
		goto put_first;
	}
	for (i = 0; i < count; i++) {
		ret = of_property_read_u32_index(first, "batt-id-list", i, &target);
		if (ret)
			goto put_first;
		if (target > 10000) {
			ret = -EINVAL;
			goto put_first;
		}
		if ((resistance < 10 && abs(resistance - (int)target) < 5) ||
		    (resistance >= target * 80 / 100 && resistance <= target * 120 / 100)) {
			match = i;
			break;
		}
	}
	ret = match < 0 ? -ENODATA : 0;
put_first:
	of_node_put(first);
	if (ret)
		return ERR_PTR(ret);
	snprintf(name, sizeof(name), "monitored-battery-%d", match);
	battery = of_parse_phandle(owner, name, 0);
	if (!battery)
		return ERR_PTR(-EINVAL);
	if (!of_device_is_compatible(battery, "simple-battery")) {
		of_node_put(battery);
		return ERR_PTR(-EINVAL);
	}
	*index = match;
	*id_mv = mv;
	return battery;
}
#endif
