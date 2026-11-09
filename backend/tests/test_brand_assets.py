"""Brand asset smoke checks: verify the approved logo/icon wiring without external libraries."""
from pathlib import Path
import json
import struct
import unittest
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parents[2]
WEB=BASE/'backend/static'

class BrandAssetsTests(unittest.TestCase):
    def png(self,path,expected_size):
        data=path.read_bytes()
        self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II',data[16:24]),(expected_size,expected_size))
        self.assertGreater(len(data),1000)

    def test_web_logo_is_original_artwork_and_not_cropped(self):
        self.png(WEB/'assets/edgepilot-brand.png',512)
        text=(WEB/'index.html').read_text()
        self.assertIn('src="/assets/edgepilot-brand.png"',text)
        self.assertIn('class="brand-art"',text)
        self.assertIn('object-fit:contain',text)
        self.assertNotIn('object-fit:cover',text)

    def test_web_icons_and_manifest_sizes(self):
        for path,size in [('favicon.png',32),('apple-touch-icon.png',180),('icon-192.png',192),('icon-512.png',512),('icon-maskable-512.png',512)]:
            self.png(WEB/path,size)
        manifest=json.loads((WEB/'manifest.webmanifest').read_text())
        self.assertEqual({x['purpose'] for x in manifest['icons']},{'any','maskable'})
        for item in manifest['icons']:
            self.assertTrue((WEB/item['src'].lstrip('/')).is_file())

    def test_android_approved_density_icons_and_adaptive_launcher(self):
        res=BASE/'android/app/src/main/res'
        for density,size in [('mdpi',48),('hdpi',72),('xhdpi',96),('xxhdpi',144),('xxxhdpi',192)]:
            self.png(res/f'mipmap-{density}/ic_launcher.png',size)
        self.png(res/'drawable-nodpi/ic_launcher_foreground.png',432)
        ET.parse(res/'mipmap-anydpi-v26/ic_launcher.xml')
        ET.parse(res/'values/colors.xml')
        manifest=(BASE/'android/app/src/main/AndroidManifest.xml').read_text()
        self.assertIn('@mipmap/ic_launcher',manifest)
        self.assertNotIn('@drawable/edgepilot_icon',manifest)

    def test_release_version_and_unmodified_trading_guard(self):
        self.assertEqual((BASE/'VERSION').read_text().strip(),'0.2.6')
        self.assertIn('versionCode = 1915',(BASE/'android/app/build.gradle.kts').read_text())
        app=(BASE/'backend/app.py').read_text()
        self.assertIn('0.2.6-observation-auto-refresh',app)
        self.assertIn("@app.post('/api/order/submit')",app)
        self.assertIn("def submit():",app)

if __name__=='__main__':
    unittest.main()
