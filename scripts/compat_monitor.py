#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy Cross-Platform Compatibility & Encryption Scheme Remote Monitor
Runs on GitHub Actions (macOS & Windows matrix) every 2 days.
Validates:
1. Tencent official release API and latest version downloadability.
2. Tencent Auth API contracts (state, token polling, token refresh).
3. WorkBuddy native application package (app.asar) invariants:
   - Storage location: CodeBuddyExtension / workbuddy-desktop
   - Encryption envelope scheme: $wbEncrypted, suite 1, sym-v1, WBEV1
   - Crypto primitives: AES-256-GCM
4. WorkBuddy Toolkit self-diagnosis (doctor).

If any check fails, writes a failure report to 'monitor_failure_report.txt'
and exits with code 1 to trigger CI email alerts.
"""

import os
import sys
import json
import time
import shutil
import zipfile
import platform
import tempfile
import traceback
import subprocess
import urllib.request
import urllib.error

REPORT_FILE = os.path.abspath("monitor_failure_report.txt")
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.path.join(REPO_DIR, "bin", "workbuddy")

CLIENT_USER_AGENT = "WorkBuddy/5.6.2"

def log(msg, level="INFO"):
    prefix = {
        "INFO": "[\033[94mINFO\033[0m]",
        "SUCCESS": "[\033[92mPASS\033[0m]",
        "WARN": "[\033[93mWARN\033[0m]",
        "FAIL": "[\033[91mFAIL\033[0m]"
    }.get(level, f"[{level}]")
    print(f"{prefix} {msg}", flush=True)

def record_failure(step_name, error_msg, details=None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    os_name = sys.platform
    arch = platform.machine()

    report_lines = [
        "==================================================================",
        "🚨 WORKBUDDY COMPATIBILITY MONITOR FAILURE REPORT",
        "==================================================================",
        f"Timestamp   : {timestamp}",
        f"Platform    : {os_name} ({arch})",
        f"Python      : {sys.version.split()[0]}",
        f"Failed Step : {step_name}",
        f"Error       : {error_msg}",
        "------------------------------------------------------------------"
    ]
    if details:
        report_lines.append("Technical Details:")
        report_lines.append(str(details))
        report_lines.append("------------------------------------------------------------------")
    report_lines.append("Action Required:")
    report_lines.append("1. Inspect changes in WorkBuddy's update payload or Tencent API.")
    report_lines.append("2. If encryption scheme changed, update AUTH_HELPER_JS in bin/workbuddy.")
    report_lines.append("3. If auth endpoints migrated, update API URLs.")
    report_lines.append("==================================================================\n")

    full_report = "\n".join(report_lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(full_report)
    log(f"Failure report written to: {REPORT_FILE}", "FAIL")
    print(full_report, file=sys.stderr)

def get_platform_id():
    if sys.platform == "darwin":
        arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "x64"
        return f"workbuddy-darwin-{arch}"
    elif sys.platform == "win32":
        return "workbuddy-win32-x64-user"
    else:
        return "workbuddy-darwin-arm64"

def step_check_update_api(platform_id):
    log(f"1. Querying Tencent Update API for platform: {platform_id} ...")
    current_ver = "5.0.0"
    latest_info = None
    hops = 0

    while hops < 5:
        hops += 1
        url = f"https://copilot.tencent.com/v2/update?platform={platform_id}&version={current_ver}"
        req = urllib.request.Request(url, headers={"User-Agent": f"WorkBuddy/{current_ver}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8").strip()
                if not raw:
                    break
                data = json.loads(raw)
                next_ver = data.get("version")
                if not next_ver or next_ver == current_ver:
                    break
                latest_info = data
                parts = next_ver.split(".")
                current_ver = ".".join(parts[:3]) if len(parts) >= 3 else next_ver
        except urllib.error.HTTPError as e:
            if e.code == 204:
                break
            raise RuntimeError(f"Update API HTTP {e.code} for {platform_id} at {current_ver}")
        except json.JSONDecodeError:
            break

    if not latest_info:
        raise ValueError(f"Could not resolve latest release for {platform_id}")

    version = latest_info.get("version") or latest_info.get("productVersion")
    download_url = latest_info.get("url")

    if not version or not download_url:
        raise ValueError(f"Invalid update API response format: {latest_info}")

    if not download_url.startswith("https://"):
        raise ValueError(f"Insecure or invalid download URL: {download_url}")

    log(f"Latest WorkBuddy Release: v{version}", "SUCCESS")
    log(f"Download URL: {download_url[:65]}...", "SUCCESS")
    return version, download_url

def step_check_auth_endpoints():
    log("2. Verifying Tencent Auth API contracts & invariant routes ...")

    # 2.1 State Endpoint
    state_url = "https://copilot.tencent.com/v2/plugin/auth/state?platform=workbuddy"
    req_state = urllib.request.Request(
        state_url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-No-Authorization": "true",
            "X-No-User-Id": "true",
            "X-No-Enterprise-Id": "true",
            "X-No-Department-Info": "true",
            "User-Agent": CLIENT_USER_AGENT
        }
    )
    with urllib.request.urlopen(req_state, timeout=12) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        if res.get("code") != 0 or not res.get("data", {}).get("state") or not res.get("data", {}).get("authUrl"):
            raise ValueError(f"State endpoint invariant violated: {res}")
    log("Auth State endpoint responsive (code: 0, state and authUrl returned)", "SUCCESS")

    # 2.2 Token Polling Endpoint (Check route is active)
    token_url = "https://copilot.tencent.com/v2/plugin/auth/token?state=compat_monitor_probe"
    req_token = urllib.request.Request(
        token_url,
        headers={
            "X-No-Authorization": "true",
            "X-No-User-Id": "true",
            "X-No-Enterprise-Id": "true",
            "X-No-Department-Info": "true",
            "User-Agent": CLIENT_USER_AGENT
        }
    )
    with urllib.request.urlopen(req_token, timeout=12) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        # 11217: login ing..., 11218: state expired, or 0
        if "code" not in res or res.get("code") not in (0, 11217, 11218):
            raise ValueError(f"Token poll endpoint invariant violated: {res}")
    log(f"Token Poll endpoint responsive (code: {res.get('code')})", "SUCCESS")

    # 2.3 Token Refresh Endpoint (Check route exists)
    refresh_url = "https://copilot.tencent.com/v2/plugin/auth/token/refresh"
    req_refresh = urllib.request.Request(
        refresh_url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Refresh-Token": "probe_dummy_refresh_token",
            "X-Auth-Refresh-Source": "plugin",
            "User-Agent": CLIENT_USER_AGENT
        }
    )
    try:
        with urllib.request.urlopen(req_refresh, timeout=12) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if "code" not in res:
                raise ValueError(f"Refresh endpoint unexpected body: {res}")
    except urllib.error.HTTPError as e:
        if e.code in (404, 502, 503):
            raise RuntimeError(f"Refresh endpoint HTTP error: {e.code}")
    log("Token Refresh endpoint route active", "SUCCESS")

def step_check_package_invariants(download_url):
    log(f"3. Downloading and inspecting application package ({download_url[:50]}...) ...")
    temp_dir = tempfile.mkdtemp(prefix="wb_monitor_")

    try:
        pkg_name = os.path.basename(download_url.split("?")[0])
        pkg_path = os.path.join(temp_dir, pkg_name)

        t0 = time.time()
        log(f"Downloading {pkg_name} ...")
        urllib.request.urlretrieve(download_url, pkg_path)
        dl_time = round(time.time() - t0, 2)
        pkg_size_mb = round(os.path.getsize(pkg_path) / (1024 * 1024), 1)
        log(f"Downloaded {pkg_size_mb} MB in {dl_time}s", "SUCCESS")

        asar_path = None

        if sys.platform == "darwin" or pkg_name.endswith(".zip"):
            log("Extracting app.asar from macOS release zip ...")
            with zipfile.ZipFile(pkg_path, "r") as z:
                asar_entry = None
                for name in z.namelist():
                    if name.endswith("Resources/app.asar"):
                        asar_entry = name
                        break
                if not asar_entry:
                    raise FileNotFoundError(f"Could not locate Resources/app.asar in zip archive (files: {z.namelist()[:5]})")
                z.extract(asar_entry, temp_dir)
                asar_path = os.path.join(temp_dir, asar_entry)

        elif sys.platform == "win32" or pkg_name.endswith(".exe"):
            log("Extracting app.asar from Windows NSIS release installer ...")
            seven_zip = shutil.which("7z") or r"C:\Program Files\7-Zip\7z.exe"
            if not os.path.exists(seven_zip) and not shutil.which("7z"):
                raise RuntimeError("7-Zip (7z) not found in PATH or standard installation directory on Windows")

            # 1. 尝试直接提取 app.asar
            subprocess.run([seven_zip, "e", pkg_path, "app.asar", "-r", f"-o{temp_dir}", "-y"], capture_output=True, text=True)

            # 2. 若未直接命中，解压嵌套 7z 包并再次提取 (Electron-builder NSIS 规范: $PLUGINSDIR/app-64.7z)
            candidate = os.path.join(temp_dir, "app.asar")
            if not os.path.exists(candidate):
                subprocess.run([seven_zip, "e", pkg_path, "*.7z", "-r", f"-o{temp_dir}", "-y"], capture_output=True, text=True)
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        if f.endswith(".7z"):
                            nested_7z = os.path.join(root, f)
                            subprocess.run([seven_zip, "e", nested_7z, "app.asar", "-r", f"-o{temp_dir}", "-y"], capture_output=True, text=True)
                            if os.path.exists(candidate):
                                break

            # 3. 全局递归定位 app.asar
            for root, _, files in os.walk(temp_dir):
                if "app.asar" in files:
                    asar_path = os.path.join(root, "app.asar")
                    break

        if not asar_path or not os.path.exists(asar_path):
            raise FileNotFoundError(f"app.asar was not successfully extracted to {asar_path}")

        asar_size_mb = round(os.path.getsize(asar_path) / (1024 * 1024), 1)
        log(f"app.asar extracted successfully ({asar_size_mb} MB)", "SUCCESS")

        # 扫描关键凭据与加密特征不变式
        log("Scanning app.asar for credential storage and encryption scheme invariants ...")
        with open(asar_path, "rb") as f:
            asar_bytes = f.read()

        invariants = {
            "Storage directory basename ('CodeBuddyExtension')": b"CodeBuddyExtension",
            "Auth profile basename ('workbuddy-desktop')": b"workbuddy-desktop",
            "Encrypted envelope marker ('$wbEncrypted')": b"$wbEncrypted",
            "Encryption scheme identifier ('sym-v1')": b"sym-v1",
            "Version suite header ('WBEV1')": b"WBEV1",
            "Native cipher algorithm ('aes-256-gcm')": b"aes-256-gcm"
        }

        missing = []
        for desc, marker in invariants.items():
            if marker in asar_bytes:
                log(f"  ✔ {desc}: MATCHED", "SUCCESS")
            else:
                log(f"  ✖ {desc}: MISSING", "FAIL")
                missing.append(desc)

        if missing:
            raise AssertionError(f"Compatibility regression detected! Missing invariant markers in latest app.asar: {missing}")

        log("All 6 storage and encryption invariants perfectly intact in the latest official release!", "SUCCESS")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def step_check_toolkit_doctor():
    log("4. Running WorkBuddy Toolkit Doctor self-diagnosis ...")
    res = subprocess.run([sys.executable, BIN_PATH, "doctor"], capture_output=True, text=True)
    if "WorkBuddy Toolkit Doctor" not in res.stdout:
        raise RuntimeError(f"Doctor failed to run:\nStdout: {res.stdout}\nStderr: {res.stderr}")
    log("WorkBuddy Toolkit Doctor executed successfully and diagnostic output verified.", "SUCCESS")

def main():
    print("==================================================================", flush=True)
    print("🚀 WorkBuddy Cross-Platform Compatibility & Encryption Remote Monitor", flush=True)
    print(f"Platform: {sys.platform} ({platform.machine()}) | Python: {sys.version.split()[0]}", flush=True)
    print("==================================================================\n", flush=True)

    platform_id = get_platform_id()

    try:
        version, download_url = step_check_update_api(platform_id)
        step_check_auth_endpoints()
        step_check_package_invariants(download_url)
        step_check_toolkit_doctor()

        print("\n==================================================================", flush=True)
        log(f"ALL MONITOR CHECKS PASSED FOR WORKBUDDY v{version} ON {sys.platform.upper()}!", "SUCCESS")
        print("==================================================================", flush=True)

        if os.path.exists(REPORT_FILE):
            try:
                os.remove(REPORT_FILE)
            except Exception:
                pass
        sys.exit(0)

    except Exception as e:
        log(f"Exception during monitor execution: {e}", "FAIL")
        record_failure(
            step_name="WorkBuddy Remote Compatibility Verification",
            error_msg=str(e),
            details=traceback.format_exc()
        )
        sys.exit(1)

if __name__ == "__main__":
    main()
