from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

# v9 fixes v8 timing. v8 queued the translation on ClipboardCaptureActivity's
# own Handler after calling finish(), but onDestroy() removes that Handler's
# callbacks. Use a separate main-looper Handler for the delayed translation.
svc=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=svc.read_text().replace('v8 service connected. Gmail uses normal Android selection. In ElevenReader: select text, tap Copy, stay in ElevenReader, then LT + RU appears as an overlay.', 'v9 service connected. Gmail uses normal Android selection. In ElevenReader: select text, tap Copy, stay in ElevenReader, then LT + RU appears as an overlay.')
svc.write_text(s)

cap=root/'app/src/main/java/lt/skarda/dualtranslate/ClipboardCaptureActivity.java'
s=cap.read_text()
old='''final String captured = text;\n                    finishWithoutAnimation();\n                    handler.postDelayed(() -> SelectionTranslateService.submitExternalSelection(captured, "ElevenReader manual Copy trigger"), 180);\n                    return;'''
new='''final String captured = text;\n                    new Handler(Looper.getMainLooper()).postDelayed(() ->\n                            SelectionTranslateService.submitExternalSelection(captured, "ElevenReader manual Copy trigger"), 220);\n                    finishWithoutAnimation();\n                    return;'''
if old not in s:
    raise RuntimeError('v8 delayed clipboard block not found')
s=s.replace(old,new,1)
cap.write_text(s)

b=root/'app/build.gradle'
s=b.read_text().replace("applicationId 'lt.skarda.dualtranslate.v8'", "applicationId 'lt.skarda.dualtranslate.v9'").replace('versionCode 8','versionCode 9').replace("versionName '8.0'","versionName '9.0'")
b.write_text(s)

for fp in ['app/src/main/AndroidManifest.xml','app/src/main/res/values/strings.xml','app/src/main/java/lt/skarda/dualtranslate/MainActivity.java','app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java']:
    q=root/fp
    z=q.read_text().replace('Dual Translate v8','Dual Translate v9')
    q.write_text(z)
