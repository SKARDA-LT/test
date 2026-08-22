from pathlib import Path
import sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')

svc=root/'app/src/main/java/lt/skarda/dualtranslate/SelectionTranslateService.java'
s=svc.read_text()
# Imports needed for gesture injection / screen bounds.
s=s.replace('import android.graphics.PixelFormat;\n', 'import android.graphics.PixelFormat;\nimport android.graphics.Path;\nimport android.graphics.Rect;\n')
# v10 state
s=s.replace('    private long clipboardCaptureCooldownUntil;\n', '    private long clipboardCaptureCooldownUntil;\n    private long elevenAutoCopyCooldownUntil;\n    private long elevenToolbarSeenAt;\n')
# Keep v9 service message but add auto-copy diagnostics.
s=s.replace('v9 service connected. Gmail uses normal Android selection. In ElevenReader: select text, tap Copy, stay in ElevenReader, then LT + RU appears as an overlay.', 'v10 service connected. Gmail uses normal Android selection. In ElevenReader v10 first tries to tap Copy automatically; manual Copy remains a fallback.')

# When ElevenReader events arrive, scan all windows after the custom toolbar has had time to appear.
needle='''        if (type == AccessibilityEvent.TYPE_TOUCH_INTERACTION_END) {\n            handler.postDelayed(this::scanActiveWindowForSelection, 100);\n            handler.postDelayed(this::scanForSelectionUi, 140);\n            if (isElevenReader) {\n                handler.postDelayed(this::scanForSelectionUi, 320);\n                handler.postDelayed(this::scanForSelectionUi, 620);\n                handler.postDelayed(this::scanForSelectionUi, 900);\n            }\n            return;\n        }'''
repl='''        if (type == AccessibilityEvent.TYPE_TOUCH_INTERACTION_END) {\n            handler.postDelayed(this::scanActiveWindowForSelection, 100);\n            handler.postDelayed(this::scanForSelectionUi, 140);\n            if (isElevenReader) {\n                handler.postDelayed(this::tryElevenReaderAutoCopy, 180);\n                handler.postDelayed(this::tryElevenReaderAutoCopy, 420);\n                handler.postDelayed(this::tryElevenReaderAutoCopy, 720);\n                handler.postDelayed(this::tryElevenReaderAutoCopy, 1050);\n            }\n            return;\n        }'''
if needle in s:
    s=s.replace(needle,repl,1)

# Also scan after ElevenReader window/content changes; this helps when selection doesn't emit touch end.
needle2='''        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED ||\n                type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||\n                type == AccessibilityEvent.TYPE_WINDOWS_CHANGED ||\n                type == AccessibilityEvent.TYPE_VIEW_CLICKED) {'''
repl2='''        if (isElevenReader && (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED ||\n                type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||\n                type == AccessibilityEvent.TYPE_WINDOWS_CHANGED)) {\n            handler.postDelayed(this::tryElevenReaderAutoCopy, 120);\n            handler.postDelayed(this::tryElevenReaderAutoCopy, 360);\n        }\n\n        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED ||\n                type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||\n                type == AccessibilityEvent.TYPE_WINDOWS_CHANGED ||\n                type == AccessibilityEvent.TYPE_VIEW_CLICKED) {'''
if needle2 in s:
    s=s.replace(needle2,repl2,1)

# Insert robust ElevenReader auto-copy implementation before clipboard handler.
anchor='    private void handleClipboardChanged() {'
helper=r'''    private void tryElevenReaderAutoCopy() {
        long now = SystemClock.uptimeMillis();
        if (now < elevenAutoCopyCooldownUntil) return;

        // Only act while ElevenReader is actually foreground.
        String activePackage = lastForegroundPackage;
        try {
            AccessibilityNodeInfo active = getRootInActiveWindow();
            if (active != null && active.getPackageName() != null) activePackage = active.getPackageName().toString();
        } catch (Exception ignored) {}
        if (!ELEVEN_READER_PACKAGE.equals(activePackage)) return;

        AccessibilityNodeInfo copy = null;
        AccessibilityNodeInfo selectAll = null;
        AccessibilityNodeInfo pronunciation = null;
        try {
            java.util.List<android.view.accessibility.AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (android.view.accessibility.AccessibilityWindowInfo w : windows) {
                    AccessibilityNodeInfo r = null;
                    try { r = w.getRoot(); } catch (Exception ignored) {}
                    if (r == null) continue;
                    if (copy == null) copy = findNode(r, "Copy", true);
                    if (selectAll == null) selectAll = findNode(r, "Select all", true);
                    if (pronunciation == null) pronunciation = findNode(r, "Add pronunciation", true);
                    if (copy != null && selectAll != null && pronunciation != null) break;
                }
            }
        } catch (Exception ignored) {}

        // First choice: if Android exposes Copy as an accessibility node, click it directly.
        if (copy != null && selectAll != null && pronunciation != null) {
            elevenToolbarSeenAt = now;
            Rect b = new Rect();
            try { copy.getBoundsInScreen(b); } catch (Exception ignored) {}
            if (clickNodeOrParent(copy)) {
                elevenAutoCopyCooldownUntil = now + 2600;
                saveDiagnostic("v10: ElevenReader toolbar found; Copy clicked through Accessibility node. Waiting for clipboard.");
                handler.postDelayed(this::handleClipboardChanged, 120);
                return;
            }
            // If semantic click is rejected, inject a real tap into the center of the visible Copy bounds.
            if (!b.isEmpty() && dispatchTap(b.centerX(), b.centerY(), "Copy node bounds")) {
                elevenAutoCopyCooldownUntil = now + 2600;
                saveDiagnostic("v10: ElevenReader Copy node found but semantic click failed; injected tap at Copy bounds.");
                handler.postDelayed(this::handleClipboardChanged, 160);
                return;
            }
        }

        // Second choice: Samsung/ElevenReader can render the toolbar visually without exposing its children.
        // Look for a small non-application accessibility window above the selected text and tap its left button.
        try {
            java.util.List<android.view.accessibility.AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                Rect screen = new Rect();
                try {
                    android.view.Display d = wm.getDefaultDisplay();
                    android.graphics.Point p = new android.graphics.Point();
                    d.getRealSize(p);
                    screen.set(0, 0, p.x, p.y);
                } catch (Exception ignored) {}
                for (android.view.accessibility.AccessibilityWindowInfo w : windows) {
                    Rect wb = new Rect();
                    try { w.getBoundsInScreen(wb); } catch (Exception ignored) {}
                    if (wb.isEmpty()) continue;
                    int sw = screen.width() > 0 ? screen.width() : 1080;
                    int sh = screen.height() > 0 ? screen.height() : 2400;
                    // Typical floating text toolbar: horizontally wide, short, away from the very top/bottom.
                    boolean plausible = wb.width() > sw * 0.35 && wb.width() < sw * 0.98 &&
                            wb.height() > 45 && wb.height() < sh * 0.16 &&
                            wb.top > sh * 0.08 && wb.bottom < sh * 0.88;
                    if (!plausible) continue;
                    AccessibilityNodeInfo r = null;
                    try { r = w.getRoot(); } catch (Exception ignored) {}
                    String dump = collectVisibleLabels(r, 0, 24).toLowerCase(java.util.Locale.ROOT);
                    boolean toolbarHint = dump.contains("select all") || dump.contains("add pronunciation") || dump.contains("copy");
                    if (!toolbarHint) continue;
                    int x = wb.left + Math.max(48, Math.min(wb.width() / 7, 105));
                    int y = wb.centerY();
                    if (dispatchTap(x, y, "toolbar window fallback")) {
                        elevenAutoCopyCooldownUntil = now + 2600;
                        saveDiagnostic("v10: ElevenReader toolbar window detected; injected tap on leftmost Copy position (" + x + "," + y + ").");
                        handler.postDelayed(this::handleClipboardChanged, 180);
                        return;
                    }
                }
            }
        } catch (Exception e) {
            saveDiagnostic("v10 auto-Copy scan error: " + e.getClass().getSimpleName());
        }
    }

    private boolean dispatchTap(int x, int y, String reason) {
        try {
            Path path = new Path();
            path.moveTo(x, y);
            android.accessibilityservice.GestureDescription.StrokeDescription stroke =
                    new android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, 55);
            android.accessibilityservice.GestureDescription.Builder gb =
                    new android.accessibilityservice.GestureDescription.Builder();
            gb.addStroke(stroke);
            return dispatchGesture(gb.build(), null, null);
        } catch (Exception e) {
            saveDiagnostic("v10 gesture failed (" + reason + "): " + e.getClass().getSimpleName());
            return false;
        }
    }

    private String collectVisibleLabels(AccessibilityNodeInfo node, int depth, int maxNodes) {
        if (node == null || depth > 6 || maxNodes <= 0) return "";
        StringBuilder sb = new StringBuilder();
        try {
            CharSequence t = node.getText();
            CharSequence d = node.getContentDescription();
            if (t != null) sb.append(t).append(' ');
            if (d != null) sb.append(d).append(' ');
            int count = Math.min(node.getChildCount(), 12);
            for (int i = 0; i < count && sb.length() < 600; i++) {
                AccessibilityNodeInfo c = node.getChild(i);
                sb.append(collectVisibleLabels(c, depth + 1, maxNodes - 1));
            }
        } catch (Exception ignored) {}
        return sb.toString();
    }

'''
if anchor not in s:
    raise RuntimeError('clipboard handler anchor not found')
s=s.replace(anchor, helper+anchor,1)
svc.write_text(s)

# v10 identity
b=root/'app/build.gradle'
s=b.read_text().replace("applicationId 'lt.skarda.dualtranslate.v9'", "applicationId 'lt.skarda.dualtranslate.v10'").replace('versionCode 9','versionCode 10').replace("versionName '9.0'","versionName '10.0'")
b.write_text(s)
for fp in ['app/src/main/AndroidManifest.xml','app/src/main/res/values/strings.xml','app/src/main/java/lt/skarda/dualtranslate/MainActivity.java','app/src/main/java/lt/skarda/dualtranslate/TextReceiverActivity.java']:
    q=root/fp
    z=q.read_text().replace('Dual Translate v9','Dual Translate v10')
    z=z.replace('waits for you to tap Copy in ElevenReader, then shows the translation over ElevenReader without opening the app full-screen.', 'tries to press Copy automatically in ElevenReader. If ElevenReader blocks the automatic tap, manual Copy still works as a fallback.')
    q.write_text(z)
