from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

svc=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=svc.read_text()

# v11: never capture clipboard merely because an automatic tap/click was attempted.
# Translation is triggered only by the real ClipboardManager.OnPrimaryClipChangedListener.
s=s.replace('                handler.postDelayed(this::handleClipboardChanged, 120);\n                return;','                return;',1)
s=s.replace('                handler.postDelayed(this::handleClipboardChanged, 160);\n                return;','                return;',1)
s=s.replace('                        handler.postDelayed(this::handleClipboardChanged, 180);\n                        return;','                        return;',1)

s=s.replace('v10 service connected. Gmail uses normal Android selection. In ElevenReader v10 first tries to tap Copy automatically; manual Copy remains a fallback.',
'''v11 service connected. Gmail uses normal Android selection. In ElevenReader v11 tries automatic Copy, but translates only after Android confirms a real clipboard change. Manual Copy remains a fallback.''')

# Improve diagnostics so a missed gesture never looks like a successful copy.
s=s.replace('saveDiagnostic("v10: ElevenReader toolbar found; Copy clicked through Accessibility node. Waiting for clipboard.");',
'''saveDiagnostic("v11: ElevenReader toolbar found; Copy click requested. Waiting for REAL clipboard-change event before translating.");''')
s=s.replace('saveDiagnostic("v10: ElevenReader Copy node found but semantic click failed; injected tap at Copy bounds.");',
'''saveDiagnostic("v11: injected tap at Copy bounds. No translation will occur unless the clipboard actually changes.");''')
s=s.replace('saveDiagnostic("v10: ElevenReader toolbar window detected; injected tap on leftmost Copy position (" + x + "," + y + ").");',
'''saveDiagnostic("v11: toolbar window detected; injected tap at presumed Copy position (" + x + "," + y + "). Waiting for real clipboard change.");''')
s=s.replace('v10 auto-Copy scan error:', 'v11 auto-Copy scan error:')
s=s.replace('v10 gesture failed (', 'v11 gesture failed (')
svc.write_text(s)

b=root/'app/build.gradle'
t=b.read_text().replace("applicationId 'lt.skarda.dualtranslate.v10'", "applicationId 'lt.skarda.dualtranslate.v11'").replace('versionCode 10','versionCode 11').replace("versionName '10.0'","versionName '11.0'")
b.write_text(t)

for fp in ['app/src/main/AndroidManifest.xml','app/src/main/res/values/strings.xml','app/src/main/java/lt/skarda/dualtranslate/MainActivity.java','app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java']:
    q=root/fp
    z=q.read_text().replace('Dual Translate v10','Dual Translate v11')
    q.write_text(z)
