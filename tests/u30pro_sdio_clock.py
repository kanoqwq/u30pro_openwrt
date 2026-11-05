"""Compile the real clock-selection/divider code against isolated CCF stubs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
DRIVER=TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/mmc/host/sdhci-sprd.c'


def function(text,name):
    start=text.rfind('\nstatic ',0,text.index(name+'('))+1
    brace=text.index('{',text.index(name+'(',start));depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


@unittest.skipUnless(os.name=='posix','native C tests run through the Linux builder')
class Clock(unittest.TestCase):
    def compile_run(self,source):
        with tempfile.TemporaryDirectory(prefix='pro-sdio-clock-') as directory:
            path=Path(directory);(path/'test.c').write_text(source)
            result=subprocess.run(['gcc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-unused-parameter',str(path/'test.c'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(path/'test')],check=True,timeout=5)

    def test_real_parent_selection_guards_errors_and_clock_reference_lifetime(self):
        helper=function(DRIVER.read_text(),'sdhci_sprd_wifi_clock')
        self.compile_run(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#define CLK_V4NRPLL_409M6 15
#define EPROBE_DEFER 517
struct device { int unused; };
struct clk { unsigned long rate; };
struct of_phandle_args { void *np; int args_count; int args[1]; };
struct sdhci_sprd_host { bool r11p3_trial,sdio_host; struct clk *clk_sdio; };
static struct clk source,output;
static int missing,deferred,parent_error,rate_error,lookups,selected,rated,put,nput;
#define IS_ERR(p) ((intptr_t)(p)<0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define dev_err_probe(dev,error,...) (error)
#define dev_info(...) ((void)0)
static void *of_find_compatible_node(void *a,void *b,const char *name) {
 assert(!strcmp(name,"sprd,ums9632-g5l-pll"));lookups++;return missing?0:&source;
}
static struct clk *of_clk_get_from_provider(struct of_phandle_args *a) {
 assert(a->args_count==1 && a->args[0]==15 && a->np==&source);
 return deferred?(struct clk *)(intptr_t)-EPROBE_DEFER:&source;
}
static void of_node_put(void *n) { assert(n==&source);nput++; }
static unsigned long clk_get_rate(struct clk *c) { return c->rate; }
static void clk_put(struct clk *c) { assert(c==&source);put++; }
static int clk_set_parent(struct clk *c,struct clk *p) {
 assert(c==&output && p==&source);selected++;return parent_error;
}
static int clk_set_rate(struct clk *c,unsigned long rate) {
 assert(c==&output && rate==409600000UL);rated++;
 if(rate_error)return rate_error;
 c->rate=rate;return 0;
}
HELPER
static void reset(void) {
 missing=deferred=parent_error=rate_error=lookups=selected=rated=put=nput=0;
 source.rate=409600000UL;output.rate=390000000UL;
}
int main(void) {
 struct device dev={0};struct sdhci_sprd_host host={true,true,&output};
 reset();host.sdio_host=false;assert(!sdhci_sprd_wifi_clock(&dev,&host));assert(!lookups);
 host.sdio_host=true;host.r11p3_trial=false;assert(!sdhci_sprd_wifi_clock(&dev,&host));assert(!lookups);
 host.r11p3_trial=true;assert(!sdhci_sprd_wifi_clock(&dev,&host));
 assert(output.rate==409600000UL && selected==1 && rated==1 && put==1 && nput==1);
 reset();missing=1;assert(sdhci_sprd_wifi_clock(&dev,&host)==-ENODEV);assert(!selected && !put);
 reset();deferred=1;assert(sdhci_sprd_wifi_clock(&dev,&host)==-EPROBE_DEFER);assert(!selected && !put && nput==1);
 reset();source.rate=400000000UL;assert(sdhci_sprd_wifi_clock(&dev,&host)==-EINVAL);assert(!selected && !rated && put==1);
 reset();parent_error=-EBUSY;assert(sdhci_sprd_wifi_clock(&dev,&host)==-EBUSY);assert(selected==1 && !rated && put==1);
 reset();rate_error=-EINVAL;assert(sdhci_sprd_wifi_clock(&dev,&host)==-EINVAL);assert(selected==1 && rated==1 && put==1);
 return 0;
}
'''.replace('HELPER',helper))

    def test_actual_controller_divider_and_reported_bus_rate(self):
        text=DRIVER.read_text()
        self.compile_run(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
typedef uint32_t u32;
#define SDHCI_SPRD_CLK_MAX_DIV 1023
#define SDHCI_CLOCK_CONTROL 0
#define SDHCI_SPRD_REG_32_BUSY_POSI 1
#define SDHCI_SPRD_BIT_OUTR_CLK_AUTO_EN 1
#define SDHCI_SPRD_BIT_INNR_CLK_AUTO_EN 2
struct sdhci_sprd_host { unsigned int base_rate; bool sdio_host; };
struct mmc_host { unsigned int actual_clock; };
struct sdhci_host { struct mmc_host *mmc;struct sdhci_sprd_host *private; };
#define TO_SPRD_HOST(h) ((h)->private)
static unsigned int encoded;
static void sdhci_writew(struct sdhci_host *h,u32 v,int r) { (void)h;(void)v;(void)r; }
static u32 sdhci_readl(struct sdhci_host *h,int r) { (void)h;(void)r;return 3; }
static void sdhci_writel(struct sdhci_host *h,u32 v,int r) { (void)h;(void)v;(void)r; }
static void sdhci_enable_clk(struct sdhci_host *h,u32 v) { (void)h;encoded=v; }
@@DIVIDER@@
@@CLOCK@@
int main(void) {
 struct mmc_host mmc={0};struct sdhci_sprd_host priv={409600000,true};struct sdhci_host h={&mmc,&priv};
 _sdhci_sprd_set_clock(&h,204800000);assert(mmc.actual_clock==204800000 && encoded==0);
 _sdhci_sprd_set_clock(&h,208000000);assert(mmc.actual_clock==204800000);
 _sdhci_sprd_set_clock(&h,100000000);assert(mmc.actual_clock==51200000 && encoded==0x200);
 _sdhci_sprd_set_clock(&h,52000000);assert(mmc.actual_clock==51200000);
 _sdhci_sprd_set_clock(&h,400000);assert(mmc.actual_clock==400000);
 priv.base_rate=390000000;_sdhci_sprd_set_clock(&h,208000000);assert(mmc.actual_clock==195000000);
 priv.sdio_host=false;mmc.actual_clock=123;_sdhci_sprd_set_clock(&h,52000000);assert(mmc.actual_clock==123);
 return 0;
}
'''.replace('@@DIVIDER@@',function(text,'sdhci_sprd_calc_div')).replace('@@CLOCK@@',function(text,'_sdhci_sprd_set_clock')))

    def test_parent_is_selected_before_cached_base_and_card_enumeration(self):
        source=DRIVER.read_text()
        parent=source.index('ret = sdhci_sprd_wifi_clock(&pdev->dev, sprd_host);')
        cached=source.index('sprd_host->base_rate = clk_get_rate(sprd_host->clk_sdio);')
        self.assertLess(parent,cached)
        self.assertIn('host->mmc->actual_clock = 0;',source)


if __name__=='__main__':unittest.main(verbosity=2)
