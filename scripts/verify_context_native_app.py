import time
from pathlib import Path
from laya import Router

target = Path("/Users/angshuman/git/Native-App")
r = Router(preload=True, device="mps")

print("=================================================================")
print("  PROOFS & VERIFICATION: Laya Context Size & Performance in Native-App")
print("=================================================================\n")

q_sec = {
    "has_secret": {
        "type": "noul",
        "instructions": "Does this file or code snippet contain raw leaked secrets, API keys, private tokens, or passwords?"
    }
}

test_files = [
    ("package.json", target / "package.json"),
    ("drizzle.config.ts", target / "drizzle.config.ts"),
    ("tamagui.config.ts", target / "tamagui.config.ts"),
    ("README.md", target / "README.md"),
]

print("1. REAL NATIVE-APP FILES SCAN (Single Window ~1,200 chars / ~300 tokens):")
for name, path in test_files:
    text = path.read_text(errors="replace")
    t0 = time.perf_counter()
    res = r.predict(text[:1200], q_sec)
    ms = (time.perf_counter() - t0) * 1000
    score = res["answers"]["has_secret"]["noul"]
    status = "BLOCKED" if score >= 0.70 else "ALLOWED (CLEAN)"
    print(f"   - {name:18} | Size: {len(text):5} chars | Latency: {ms:5.1f} ms | Score: {score:.4f} -> {status}")

print("\n2. ACCURACY TEST: INJECTING LEAKED SECRET IN NATIVE-APP CODE:")
leak_snippet = (
    "// Native-App Expo Auth Config\n"
    "const EXPO_PUBLIC_GITHUB_TOKEN = 'ghp_9876543210abcdef9876543210abcdef9876';\n"
    "export default EXPO_PUBLIC_GITHUB_TOKEN;\n"
)
t0 = time.perf_counter()
res_leak = r.predict(leak_snippet, q_sec)
ms = (time.perf_counter() - t0) * 1000
score_leak = res_leak["answers"]["has_secret"]["noul"]
status = "BLOCKED" if score_leak >= 0.70 else "ALLOWED"
print(f"   - Leaked Token Snippet  | Size: {len(leak_snippet):5} chars | Latency: {ms:5.1f} ms | Score: {score_leak:.4f} -> {status}")

print("\n3. CONTEXT SIZE VERIFICATION (predict vs predict_long across full multi-KB file):")
full_readme = (target / "README.md").read_text()
t0 = time.perf_counter()
res_short = r.predict(full_readme[:1200], q_sec)
ms_short = (time.perf_counter() - t0) * 1000

t0 = time.perf_counter()
res_long = r.predict_long(full_readme, q_sec)
ms_long = (time.perf_counter() - t0) * 1000

score_short = res_short["answers"]["has_secret"]["noul"]
score_long = res_long["answers"]["has_secret"]["noul"]
windows = res_long["usage"]["windows"]

print(f"   - predict (first window 1,200 chars) : {ms_short:5.1f} ms | Score: {score_short:.4f}")
print(f"   - predict_long (ENTIRE 4,386 chars)  : {ms_long:5.1f} ms | Scanned {windows} windows | Score: {score_long:.4f}")

# Secret at the very END of a 4KB file
print("\n4. BLIND SPOT TEST: Placing secret at line 100 (char 4,000) of Native-App README:")
tampered_readme = full_readme + "\n\nCRITICAL_LEAK = 'sk-proj-supersecretkey999999999999'\n"
res_tampered_short = r.predict(tampered_readme[:1200], q_sec)
res_tampered_long = r.predict_long(tampered_readme, q_sec)
score_tampered_short = res_tampered_short["answers"]["has_secret"]["noul"]
score_tampered_long = res_tampered_long["answers"]["has_secret"]["noul"]

print(f"   - Truncated (misses end of file)     : Score: {score_tampered_short:.4f} (Missed leak: {score_tampered_short < 0.70})")
print(f"   - predict_long (scans all windows)   : Score: {score_tampered_long:.4f} (Caught leak: {score_tampered_long >= 0.70})")

print("\n=================================================================\n")
