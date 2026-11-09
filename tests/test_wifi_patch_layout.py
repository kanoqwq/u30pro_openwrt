"""The DFS patch must apply to stock and SAE-patched wifi-scripts."""
import shutil
import subprocess
import tempfile
import unittest
import json
import runpy
from pathlib import Path

PATCH=Path(__file__).resolve().parents[1]/'openwrt/patches/wifi-scripts-no-dfs.patch'
BAND_PATCH=PATCH.with_name('wifi-scripts-chanlist-band.patch')
SOURCE="""import {
	append, append_raw, append_vars, dump_config, flush_config, set_default,
	wiphy_info, wiphy_band
} from 'wifi.common';
import { validate } from 'wifi.validate';
function device_capabilities(config) {
	let phy = config.phy;
	phy = wiphy_info(phy);
	let band = wiphy_band(phy, config.band);

	phy_capabilities.ht_capa = band.ht_capa ?? 0;
CIPHER}

function generate(config) {
	if (!config)
		die('unknown phy');

	set_device_defaults(config);

	device_log_append(config);
}
"""

@unittest.skipUnless(shutil.which('patch'),'requires GNU patch')
class PatchLayouts(unittest.TestCase):
    def test_stock_and_sae_generators(self):
        for cipher in ['', '\tphy_features.cipher_gcmp256 = WLAN_CIPHER_SUITE_GCMP_256 in (phy.cipher_suites ?? []);\n']:
            with self.subTest(cipher_in_hostapd=bool(cipher)),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);p=root/'usr/share/ucode/wifi/hostapd.uc';p.parent.mkdir(parents=True)
                p.write_text(SOURCE.replace('CIPHER',cipher))
                result=subprocess.run(['patch','--batch','--fuzz=0','-p1','-d',tmp,'-i',str(PATCH)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                result=subprocess.run(['patch','--batch','--fuzz=0','-p1','-d',tmp,'-i',str(BAND_PATCH)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                text=p.read_text()
                self.assertEqual(text.count('function device_no_dfs(config)'),1)
                self.assertEqual(text.count('device_no_dfs(config);'),1)
                self.assertEqual(text.count('function device_chanlist_band(config)'),1)
                self.assertEqual(text.count('device_chanlist_band(config);'),1)
                self.assertLess(text.index('device_chanlist_band(config);'),text.index('device_no_dfs(config);'))
                self.assertIn('config.channel = 36;',text)
                self.assertNotRegex(text,r'config\.htmode\s*=(?!=)')

    def test_prepared_root_migrates_once_and_checks_composed_receipts(self):
        module=runpy.run_path(str(PATCH.parents[1].parent/'tools/stage-wifi-patches.py'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'usr/share/ucode/wifi/hostapd.uc';target.parent.mkdir(parents=True)
            target.write_text(SOURCE.replace('CIPHER',''))
            subprocess.run(['patch','--batch','--fuzz=0','-p1','-d',tmp,'-i',str(PATCH)],check=True,capture_output=True)
            receipt=root/'shared-patches.json'
            receipt.write_text(json.dumps({PATCH.name:{'patch':module['digest'](PATCH),'result':module['digest'](target)}}))
            module['stage'](root,PATCH.parent,receipt)
            before=target.read_bytes();saved=receipt.read_bytes()
            module['stage'](root,PATCH.parent,receipt)
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(receipt.read_bytes(),saved)
            records=json.loads(saved)
            self.assertEqual(records[PATCH.name]['result'],records[BAND_PATCH.name]['result'])
            target.write_text(target.read_text()+'\n// unreviewed change\n')
            changed=target.read_bytes()
            with self.assertRaises(ValueError):module['stage'](root,PATCH.parent,receipt)
            self.assertEqual(target.read_bytes(),changed)

    def test_fresh_root_and_changed_patch_source(self):
        module=runpy.run_path(str(PATCH.parents[1].parent/'tools/stage-wifi-patches.py'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'usr/share/ucode/wifi/hostapd.uc';target.parent.mkdir(parents=True)
            target.write_text(SOURCE.replace('CIPHER',''))
            patch_dir=root/'patches';patch_dir.mkdir()
            for source in (PATCH,BAND_PATCH):shutil.copyfile(source,patch_dir/source.name)
            receipt=root/'shared-patches.json'
            module['stage'](root,patch_dir,receipt)
            before=target.read_bytes();saved=receipt.read_bytes()
            source=patch_dir/BAND_PATCH.name
            source.write_text(source.read_text()+'\n')
            with self.assertRaises(ValueError):module['stage'](root,patch_dir,receipt)
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(receipt.read_bytes(),saved)
