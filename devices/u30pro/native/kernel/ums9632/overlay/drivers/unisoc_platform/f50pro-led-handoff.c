// SPDX-License-Identifier: GPL-2.0-only
/*
 * MU3356 Lights HAL clears the legacy PMIC red/green emitters before using
 * its GPIO indicators. Its PMIC red/green outputs are the two WHITE emitters,
 * not the GPIO green outputs. Reproduce stock steady PWM and boot handoff.
 * Evidence: F50ProV1.0.0B22 lights-service
 * and sprd-leds-bltc.ko, recorded in docs/F50PRO-PORTING.zh-CN.md.
 */
#include <linux/module.h>
#include <linux/leds.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>

/* The shared kernel also boots MU5358. Only the F50 product autoload enables
 * this driver, so matching a common PMIC alone never changes U30 Pro LEDs.
 */
static bool enabled;
module_param(enabled, bool, 0444);
MODULE_PARM_DESC(enabled, "Enable the MU3356 stock GPIO-indicator handoff");

struct f50pro_bltc;
struct f50pro_lamp {
	struct led_classdev led;
	struct f50pro_bltc *bltc;
	u8 channel;
};
struct f50pro_bltc {
	struct regmap *map;
	u32 base;
	struct mutex lock;
	struct f50pro_lamp lamps[2];
};

static int f50pro_white_set(struct led_classdev *led, enum led_brightness brightness)
{
	struct f50pro_lamp *lamp = container_of(led, struct f50pro_lamp, led);
	struct f50pro_bltc *bltc = lamp->bltc;
	u32 mask = 3 << (lamp->channel * 4);
	int ret = 0;

	mutex_lock(&bltc->lock);
	/* Stock sprd_led_set: period 255, duty brightness, then RUN|TYPE. */
	if (brightness)
		ret = regmap_update_bits(bltc->map,
			bltc->base + 8 + lamp->channel * 16,
			0xffff, 0xff | (brightness << 8));
	if (!ret)
		ret = regmap_update_bits(bltc->map, bltc->base, mask,
					 brightness ? mask : 0);
	mutex_unlock(&bltc->lock);
	return ret;
}

static int f50pro_led_handoff_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct regmap *map;
	struct f50pro_bltc *bltc;
	u32 base, value;
	int ret, i;

	if (!enabled || !of_machine_is_compatible("sprd,ums9632"))
		return -ENODEV;
	map = dev_get_regmap(dev->parent, NULL);
	if (!map)
		return dev_err_probe(dev, -EPROBE_DEFER, "PMIC regmap unavailable\n");
	ret = of_property_read_u32(dev->of_node, "reg", &base);
	if (ret)
		return dev_err_probe(dev, ret, "Missing BLTC register base\n");
	/* Stock sprd_led_set(0): clear (RUN | TYPE) << (channel * 4).
	 * Only red=0 and green=1 belong to this HAL handoff; leave blue intact.
	 */
	ret = regmap_update_bits(map, base, 0x33, 0);
	if (!ret)
		ret = regmap_read(map, base, &value);
	if (ret)
		return dev_err_probe(dev, ret, "PMIC indicator handoff failed\n");
	if (value & 0x33)
		return dev_err_probe(dev, -EIO, "PMIC indicator handoff readback failed\n");
	/* UMP9651-specific stock global enables. Do not borrow SC2731 offsets,
	 * change LED current or alter the unused PMIC blue channel.
	 */
	ret = regmap_update_bits(map, 0x2008, BIT(9), BIT(9));
	if (!ret)
		ret = regmap_update_bits(map, 0x2010, BIT(7), BIT(7));
	if (!ret)
		ret = regmap_update_bits(map, base, BIT(12), 0);
	if (ret)
		return dev_err_probe(dev, ret, "PMIC LED clock setup failed\n");
	bltc = devm_kzalloc(dev, sizeof(*bltc), GFP_KERNEL);
	if (!bltc)
		return -ENOMEM;
	bltc->map = map;
	bltc->base = base;
	mutex_init(&bltc->lock);
	for (i = 0; i < ARRAY_SIZE(bltc->lamps); i++) {
		struct f50pro_lamp *lamp = &bltc->lamps[i];
		lamp->bltc = bltc;
		lamp->channel = i;
		lamp->led.name = i ? "sc27xx:green" : "sc27xx:red";
		lamp->led.max_brightness = 255;
		lamp->led.brightness_set_blocking = f50pro_white_set;
		ret = devm_led_classdev_register(dev, &lamp->led);
		if (ret)
			return dev_err_probe(dev, ret, "PMIC white LED registration failed\n");
	}
	dev_info(dev, "MU3356 PMIC white emitters ready; legacy state cleared\n");
	return 0;
}

static const struct of_device_id f50pro_led_handoff_match[] = {
	{ .compatible = "sprd,ump9651-bltc" },
	{ }
};
/* No modalias autoload: product-specific modules.d owns this handoff. */
static struct platform_driver f50pro_led_handoff_driver = {
	.probe = f50pro_led_handoff_probe,
	.driver = {
		.name = "f50pro-led-handoff",
		.of_match_table = f50pro_led_handoff_match,
	},
};
module_platform_driver(f50pro_led_handoff_driver);
MODULE_DESCRIPTION("F50 Pro stock PMIC white LEDs and GPIO handoff");
MODULE_LICENSE("GPL");
