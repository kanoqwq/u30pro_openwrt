// SPDX-License-Identifier: GPL-2.0-only
/* MU3356 B22 fm11tag.ko / ntag_fm11_gpio: reset is high at rest, low
 * during I2C access. Resolve the GPIO from this board's DT, never a global
 * Linux GPIO number. Only the F50 product explicitly loads this module. */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/gpio/consumer.h>
#include <linux/kobject.h>
#include <linux/sysfs.h>

static bool enabled;
module_param(enabled, bool, 0444);
static struct gpio_desc *reset_gpio;
static struct kobject *ntag_kobj;

static ssize_t reset_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%d\n", gpiod_get_raw_value_cansleep(reset_gpio));
}
static ssize_t reset_store(struct kobject *kobj, struct kobj_attribute *attr,
		const char *buf, size_t count)
{
	bool high;
	if (kstrtobool(buf, &high)) return -EINVAL;
	gpiod_set_raw_value_cansleep(reset_gpio, high);
	return count;
}
static struct kobj_attribute reset_attr = __ATTR(reset, 0600, reset_show, reset_store);

static int __init f50pro_nfc_init(void)
{
	struct device_node *node;
	int ret;
	if (!enabled || !of_machine_is_compatible("sprd,ums9632")) return -ENODEV;
	node = of_find_node_by_path("/ntag_fm11_gpio");
	if (!node) return -ENODEV;
	reset_gpio = fwnode_gpiod_get_index(of_fwnode_handle(node), "ntag-reset", 0,
		GPIOD_ASIS, "f50pro-nfc-reset");
	of_node_put(node);
	if (IS_ERR(reset_gpio)) return PTR_ERR(reset_gpio);
	if (gpiod_is_active_low(reset_gpio)) { gpiod_put(reset_gpio); return -EINVAL; }
	ret = gpiod_direction_output_raw(reset_gpio, 1);
	if (ret) { gpiod_put(reset_gpio); return ret; }
	ntag_kobj = kobject_create_and_add("f50pro_nfc", kernel_kobj);
	if (!ntag_kobj) { gpiod_put(reset_gpio); return -ENOMEM; }
	ret = sysfs_create_file(ntag_kobj, &reset_attr.attr);
	if (ret) { kobject_put(ntag_kobj); gpiod_put(reset_gpio); }
	return ret;
}
static void __exit f50pro_nfc_exit(void)
{
	sysfs_remove_file(ntag_kobj, &reset_attr.attr);
	kobject_put(ntag_kobj);
	gpiod_set_raw_value_cansleep(reset_gpio, 1);
	gpiod_put(reset_gpio);
}
module_init(f50pro_nfc_init);
module_exit(f50pro_nfc_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("F50 Pro DT-derived NFC reset ownership");
