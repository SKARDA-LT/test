from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

# Make clipboard capture an isolated temporary task and delay translation until after it closes.
p=root/'app/src/main/java/lt/skarda/dualtranslate/ClipboardCaptureActivity.java'
s=p.read_text()
s=s.replace('SelectionTranslateService.submitExternalSelection(text, "ElevenReader manual Copy trigger");\n                    finishWithoutAnimation();\n                    return;', 'final String captured = text;\n                    finishWithoutAnimation();\n                    handler.postDelayed(() -> SelectionTranslateService.submitExternalSelection(captured, "ElevenReader manual Copy trigger"), 180);\n                    return;')
p.write_text(s)

m=root/'app/src/main/AndroidManifest.xml'
s=m.read_text()
# Keep the existing noHistory setting; only isolate ClipboardCaptureActivity from the main app task.
s=s.replace('android:name=".ClipboardCaptureActivity"\n            android:exported="false"', 'android:name=".ClipboardCaptureActivity"\n            android:exported="false"\n            android:taskAffinity=""')
m.write_text(s)

# Ensure service launches capture as a separate ephemeral task.
p=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=p.read_text()
s=s.replace('Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION | Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS', 'Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NEW_DOCUMENT | Intent.FLAG_ACTIVITY_MULTIPLE_TASK | Intent.FLAG_ACTIVITY_NO_ANIMATION | Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS')
s=s.replace('v7 service connected. Gmail uses normal Android selection. In ElevenReader: select text, then tap Copy; clipboard change triggers translation.', 'v8 service connected. Gmail uses normal Android selection. In ElevenReader: select text, tap Copy, stay in ElevenReader, then LT + RU appears as an overlay.')
p.write_text(s)

b=root/'app/build.gradle'
s=b.read_text().replace("applicationId 'lt.skarda.dualtranslate.v7'","applicationId 'lt.skarda.dualtranslate.v8'").replace('versionCode 7','versionCode 8').replace("versionName '7.0'","versionName '8.0'")
b.write_text(s)

for fp in ['app/src/main/AndroidManifest.xml','app/src/main/res/values/strings.xml','app/src/main/java/lt/skarda/dualtranslate/MainActivity.java','app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java']:
    q=root/fp
    z=q.read_text().replace('Dual Translate v7','Dual Translate v8')
    z=z.replace('presses Copy automatically, and translates the selected phrase. No extra tap is required.', 'waits for you to tap Copy in ElevenReader, then shows the translation over ElevenReader without opening the app full-screen.')
    q.write_text(z)
