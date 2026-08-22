from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

svc=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=svc.read_text()

old='''            double distance = toolbar.isEmpty() ? 0 : rectDistance(b, toolbar);\n            if (distance > dp(420)) continue;\n\n            // Highlighted text has a mid-tone selection background; ordinary book text has page background.\n            double score = contrast * 5.0 - distance * 0.22 - Math.max(0, t.length() - 24) * 1.5;\n'''
new='''            double distance = toolbar.isEmpty() ? 0 : rectDistance(b, toolbar);\n            // v14: the real selected word is always very close to the Android selection toolbar.\n            // ElevenReader may keep other blue reading/highlight regions elsewhere on the page, so\n            // reject OCR text that is too far from the toolbar instead of letting contrast dominate.\n            if (!toolbar.isEmpty() && distance > dp(140)) continue;\n\n            // Prefer proximity strongly; contrast is only a secondary signal.\n            double score = contrast * 3.0 - distance * 1.6 - Math.max(0, t.length() - 24) * 1.5;\n'''
if old not in s:
    raise RuntimeError('Could not locate v13 OCR scoring block')
s=s.replace(old,new)
s=s.replace('v13:', 'v14:')
s=s.replace('v13 service connected.', 'v14 service connected.')
svc.write_text(s)

b=root/'app/build.gradle'
t=b.read_text()
t=t.replace("applicationId 'lt.skarda.dualtranslate.v13'", "applicationId 'lt.skarda.dualtranslate.v14'")
t=t.replace('versionCode 13','versionCode 14').replace("versionName '13.0'","versionName '14.0'")
b.write_text(t)

for fp in ['app/src/main/AndroidManifest.xml','app/src/main/res/values/strings.xml','app/src/main/java/lt/skarda/dualtranslate/MainActivity.java','app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java']:
    q=root/fp
    z=q.read_text().replace('Dual Translate v13','Dual Translate v14')
    q.write_text(z)
