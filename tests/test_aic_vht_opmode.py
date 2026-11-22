"""Execute the production AIC peer-opmode serializer; no device access."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
SOURCE=TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/aic8800/aic8800_fdrv/rwnx_msg_tx.c'


class PeerOperatingMode(unittest.TestCase):
    def test_preserves_all_peer_mode_bytes_and_notification_presence(self):
        source=SOURCE.read_text()
        start=source.index('if (link_sta_params->opmode_notif_used) {')
        block=source[start:source.index('\n\t}',start)+3]
        code=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#define STA_OPMOD_NOTIF (1U << 4)
struct link_station_parameters { uint8_t opmode_notif; bool opmode_notif_used; };
struct me_sta_add_req { uint8_t flags,opmode; };
static void serialize(struct link_station_parameters *link_sta_params,
                      struct me_sta_add_req *req) {
''' + block + r'''
}
int main(void) {
    const unsigned flags[]={0,1,8,0x80};
    for(unsigned used=0;used<2;used++)
        for(unsigned value=0;value<256;value++)
            for(unsigned f=0;f<sizeof(flags)/sizeof(flags[0]);f++) {
                struct link_station_parameters peer={value,used};
                struct me_sta_add_req req={flags[f],0xa5};
                serialize(&peer,&req);
                unsigned expected=used?value:0xa5;
                if(req.opmode!=expected) {
                    fprintf(stderr,"peer mode 0x%02x, present %u: firmware got 0x%02x, expected 0x%02x\n",
                            value,used,req.opmode,expected);
                    return 1;
                }
                assert(req.flags==(flags[f] | (used?STA_OPMOD_NOTIF:0)));
            }
    // IEEE 802.11 VHT opmode: width bits 0..1; RX NSS minus one in bits 4..6.
    // Preserve both an 80 MHz / 2SS peer and a legitimate 40 MHz / 1SS peer.
    for(unsigned value=0;value<=0x12;value++) {
        struct link_station_parameters peer={value,true};
        struct me_sta_add_req req={0,0};serialize(&peer,&req);
        assert((req.opmode&3)==(value&3));
        assert(((req.opmode>>4)&7)==((value>>4)&7));
    }
    puts("PASS 2048 peer opmode/presence/flag cases, including valid zero and 80MHz/2SS");
    return 0;
}
'''
        cc=shutil.which('cc')
        self.assertIsNotNone(cc,'host C compiler required for driver regression')
        with tempfile.TemporaryDirectory(prefix='aic-opmode-') as directory:
            root=Path(directory);src=root/'peer.c';binary=root/'peer'
            src.write_text(code)
            subprocess.run([cc,'-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            '-fno-pie','-no-pie',str(src),'-o',str(binary)],check=True)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
