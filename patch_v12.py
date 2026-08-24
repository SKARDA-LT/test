from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

svc=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=svc.read_text()

start=s.find('    private void tryElevenReaderAutoCopy() {')
end=s.find('    private boolean dispatchTap(', start)
if start < 0 or end < 0:
    raise RuntimeError('Could not locate ElevenReader auto-copy block')

replacement=r'''    private void tryElevenReaderAutoCopy() {
        long now = SystemClock.uptimeMillis();
        if (now < elevenAutoCopyCooldownUntil) return;

        String activePackage = lastForegroundPackage;
        try {
            AccessibilityNodeInfo active = getRootInActiveWindow();
            if (active != null && active.getPackageName() != null) activePackage = active.getPackageName().toString();
        } catch (Exception ignored) {}
        if (!ELEVEN_READER_PACKAGE.equals(activePackage)) return;

        if (tryAndroidActionCopy()) {
            elevenAutoCopyCooldownUntil = now + 2200;
            saveDiagnostic("v12: Android Accessibility ACTION_COPY succeeded on ElevenReader selected text. Waiting for real clipboard-change event.");
        } else {
            elevenAutoCopyCooldownUntil = now + 700;
            saveDiagnostic("v12: ElevenReader selection mode detected, but Android did not expose a selected text node that accepts ACTION_COPY. Manual Copy remains available.");
        }
    }

    private boolean tryAndroidActionCopy() {
        java.util.ArrayList<AccessibilityNodeInfo> roots = new java.util.ArrayList<>();
        try {
            AccessibilityNodeInfo active = getRootInActiveWindow();
            if (active != null) roots.add(active);
        } catch (Exception ignored) {}
        try {
            java.util.List<android.view.accessibility.AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (android.view.accessibility.AccessibilityWindowInfo w : windows) {
                    try {
                        AccessibilityNodeInfo r = w.getRoot();
                        if (r != null && !roots.contains(r)) roots.add(r);
                    } catch (Exception ignored) {}
                }
            }
        } catch (Exception ignored) {}

        // First, require evidence that ElevenReader is in its custom selection mode.
        boolean toolbarVisible = false;
        for (AccessibilityNodeInfo r : roots) {
            if (findNode(r, "Copy", true) != null &&
                    findNode(r, "Select all", true) != null &&
                    findNode(r, "Add pronunciation", true) != null) {
                toolbarVisible = true;
                break;
            }
        }
        if (!toolbarVisible) return false;

        // Best case: ElevenReader exposes the exact selected range on a text node.
        for (AccessibilityNodeInfo r : roots) {
            AccessibilityNodeInfo n = findSelectedTextNode(r, true, 0);
            if (n != null) {
                try {
                    if (n.performAction(AccessibilityNodeInfo.ACTION_COPY)) return true;
                } catch (Exception ignored) {}
            }
        }

        // Fallback: while the selection toolbar is visible, look for an ElevenReader text node
        // that explicitly advertises ACTION_COPY, even if it hides selection start/end.
        for (AccessibilityNodeInfo r : roots) {
            AccessibilityNodeInfo n = findSelectedTextNode(r, false, 0);
            if (n != null) {
                try {
                    if (n.performAction(AccessibilityNodeInfo.ACTION_COPY)) return true;
                } catch (Exception ignored) {}
            }
        }
        return false;
    }

    private AccessibilityNodeInfo findSelectedTextNode(AccessibilityNodeInfo node, boolean requireRange, int depth) {
        if (node == null || depth > 10) return null;
        try {
            CharSequence pkgCs = node.getPackageName();
            String pkg = pkgCs == null ? "" : pkgCs.toString();
            CharSequence textCs = node.getText();
            String text = textCs == null ? "" : textCs.toString();
            int start = node.getTextSelectionStart();
            int end = node.getTextSelectionEnd();
            boolean validRange = start >= 0 && end > start && end <= text.length();
            boolean supportsCopy = (node.getActions() & AccessibilityNodeInfo.ACTION_COPY) != 0;
            boolean isToolbarLabel = "copy".equalsIgnoreCase(text.trim()) ||
                    "select all".equalsIgnoreCase(text.trim()) ||
                    "add pronunciation".equalsIgnoreCase(text.trim());

            if (ELEVEN_READER_PACKAGE.equals(pkg) && !isToolbarLabel && !text.isEmpty()) {
                if (requireRange && validRange) return node;
                if (!requireRange && supportsCopy) return node;
            }

            int count = Math.min(node.getChildCount(), 80);
            for (int i = 0; i < count; i++) {
                AccessibilityNodeInfo c = null;
                try { c = node.getChild(i); } catch (Exception ignored) {}
                AccessibilityNodeInfo found = findSelectedTextNode(c, requireRange, depth + 1);
                if (found != null) return found;
            }
        } catch (Exception ignored) {}
        return null;
    }

'''
s=s[:start]+replacement+s[end:]

s=s.replace('v11 service connected. Gmail uses normal Android selection. In ElevenReader v11 tries automatic Copy, but translates only after Android confirms a real clipboard change. Manual Copy remains a fallback.',
'''v12 service connected. Gmail uses normal Android selection. In ElevenReader v12 uses Android Accessibility ACTION_COPY on the selected text node; manual Copy remains a fallback.''')
svc.write_text(s)

b=root/'app/build.gradle'
t=b.read_text().replace("applicationId 'lt.skarda.dualtranslate.v11'", "applicationId 'lt.skarda.dualtranslate.v12'").replace('versionCode 11','versionCode 12').replace("versionName '11.0'","versionName '12.0'")
b.write_text(t)

for fp in ['app/src/main/AndroidManifest.xml','app/src/main/res/values/strings.xml','app/src/main/java/lt/skarda/dualtranslate/MainActivity.java','app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java']:
    q=root/fp
    z=q.read_text().replace('Dual Translate v11','Dual Translate v12')
    z=z.replace('tries to press Copy automatically in ElevenReader. If ElevenReader blocks the automatic tap, manual Copy still works as a fallback.',
                'uses Android Accessibility ACTION_COPY directly on the selected ElevenReader text node. Manual Copy still works as a fallback.')
    q.write_text(z)
