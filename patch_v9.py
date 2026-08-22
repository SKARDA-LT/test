from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

# v9 fixes v8 timing: schedule the translation on the AccessibilityService handler,
# which survives after the temporary clipboard-capture activity closes.
svc=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=svc.read_text()
anchor='    public static void submitExternalSelection('
if anchor not in s:
    raise RuntimeError('submitExternalSelection anchor not found')
helper='''    public static void submitExternalSelectionAfterDelay(final String text, final String source, long delayMs) {\n        final SelectionTranslateService service = INSTANCE;\n        if (service == null || text == null || text.trim().isEmpty()) return;\n        service.handler.postDelayed(() -> submitExternalSelection(text, source), Math.max(0L, delayMs));\n    }\n\n'''
s=s.replace(anchor, helper+anchor, 1)
s=s.replace('v8 service connected. Gmail uses normal Android selection. In ElevenReader: select text, tap Copy, stay in ElevenReader, then LT + RU appears as an overlay.', 'v9 service connected. Gmail uses normal Android selection. In ElevenReader: select text, tap Copy, stay in ElevenReader, then LT + RU appears as an overlay.')
svc.write_text(s)

cap=root/'app/src/main/java/lt/skarda/dualtranslate/ClipboardCaptureActivity.java'
s=cap.read_text()
old='''final String captured = text;\n                    finishWithoutAnimation();\n                    handler.postDelayed(() -> SelectionTranslateService.submitExternalSelection(captured, "ElevenReader manual Copy trigger"), 180);\n                    return;'''
new='''final String captured = text;\n                    SelectionTranslateService.submitExternalSelectionAfterDelay(captured, "ElevenReader manual Copy trigger", 220);\n                    finishWithoutAnimation();\n                    return;'''
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
