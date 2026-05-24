# Device Fingerprint Field Mapping

## Common Device ID Fields

| API Field Name | Source | adb Command |
|---------------|--------|-------------|
| deviceId, device_id, meid, imei | Settings.Secure.ANDROID_ID | `adb shell settings get secure android_id` |
| androidId | Settings.Secure.ANDROID_ID | same |
| mac, macAddress | WifiManager | `adb shell cat /sys/class/net/wlan0/address` |

## App Version Fields

| API Field Name | Source | Extraction Method |
|---------------|--------|-------------------|
| appVersion, version, app_version | AndroidManifest.xml | apk_extract_manifest → versionName |
| appVersionCode, build, versionCode | AndroidManifest.xml | apk_extract_manifest → versionCode |
| channel | AndroidManifest.xml meta-data | Search for "channel" in manifest |
| app, appName | Package name | apk_extract_manifest → package |

## System Info Fields

| API Field Name | Source | adb Command |
|---------------|--------|-------------|
| os, platform | "Android" (fixed) | — |
| osVersion, os_version, sysVersion | Build.VERSION.RELEASE | `adb shell getprop ro.build.version.release` |
| model, device, phoneModel | Build.MODEL | `adb shell getprop ro.product.model` |
| brand | Build.BRAND | `adb shell getprop ro.product.brand` |
| netType, networkType | ConnectivityManager | Infer from proxy status |

## Strategy
1. Phase 1: adb_device_info → fill model, osVersion, androidId
2. Phase 0: apk_extract_manifest → fill version, build, channel, package
3. Phase 2: proxy_get_flow → detect actual fields used by API → fill remaining
