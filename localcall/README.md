# Local Call Style

Alarm-style **incoming call** alerts generated entirely on the device — no server, no telephony,
no SIM. Two complete apps: native Android (Kotlin) and native iOS (Swift/SwiftUI), each with
custom ringtone support.

Both demonstrate the same three use cases:

| # | Use case | Android | iOS |
|---|----------|---------|-----|
| 1 | **Instant trigger** — ring right now | `CallService.startIncoming()` | CallKit (`reportNewIncomingCall`) |
| 2 | **Scheduled trigger** — ring in 10 s, app closed | `AlarmManager.setAlarmClock` → `CallReceiver` | `UNTimeIntervalNotificationTrigger` |
| 3 | **Answer / Decline** | notification actions + full-screen activity | notification actions + CallKit |

---

## Read this first: the platforms are not equivalent

This is the single most important thing to understand before building on top of it.

**Android can genuinely do this.** A full-screen intent on a high-importance notification turns
the screen on, takes over the lock screen, and shows your own UI, from a cold start, with no
server involved. That is a real, documented capability.

**iOS cannot — not locally.** There is no `setFullScreenIntent` equivalent. An app cannot draw
over the lock screen. The only way to get the real full-screen incoming-call UI on a locked iPhone
is **CallKit**, and CallKit requires the app's process to be alive. Apple's only sanctioned way
to wake a terminated app for a call is a **PushKit VoIP push** (`PKPushRegistry`), which comes
from APNs and therefore **requires a server**. There is no offline substitute: no background task,
no timer, no silent push.

So on iOS this project gives you:

| Situation | What you get |
|---|---|
| App in foreground or background | **CallKit** — real system call screen, looping ringtone, lock-screen takeover |
| App terminated, no server | **Time-sensitive local notification** — Answer/Decline buttons, breaks through Focus, chained to keep ringing ~45 s. Banner / lock-screen entry; the user must tap it. |
| App terminated, with a server | Add PushKit + APNs VoIP certificate → full CallKit takeover. The hook is documented in `ios/Sources/CallKitManager.swift`. |

Anything that claims a local iOS app can force a full-screen call screen from a terminated state
is either using CallKit while alive, or is wrong.

---

## Custom ringtone

### Android — drop in an MP3, done

```
android/app/src/main/res/raw/ringtone.mp3
```

That is the entire setup. `RingtonePlayer` resolves the resource **by name at runtime**
(`resources.getIdentifier("ringtone", "raw", packageName)`), so the project compiles with or
without the file, and falls back to the device ringtone when it is missing.
`.mp3`, `.ogg`, `.m4a`, `.wav` all work. Length does not matter — it is looped.

`res/raw` file names must be lowercase letters, digits and underscores. `MyRing.mp3` and
`ring-tone.mp3` will fail the resource build.

### iOS — MP3 will not work

`UNNotificationSound` accepts only **`.caf` / `.aiff` / `.wav`**, **30 seconds or shorter**. Give
it an MP3 and iOS silently plays the default sound instead — no error, no warning. This is the
most common cause of "my custom iOS sound isn't working".

Convert once, for both platforms:

```bash
scripts/make-ringtone.sh ~/Downloads/my-ring.mp3
```

That writes `android/app/src/main/res/raw/ringtone.mp3` and `ios/Resources/ringtone.caf`
(trimmed to 29 s, mono, IMA4-in-CAF). Needs `afconvert` (macOS, built in) or `ffmpeg`.

Two separate iOS sounds, two separate rules:

* **Notification sound** — `UNNotificationSound(named: "ringtone.caf")`. Plays **once**; there is
  no loop flag. The app chains notifications 5 s apart to keep ringing.
* **CallKit ringtone** — `CXProviderConfiguration.ringtoneSound = "ringtone.caf"`. CallKit **does**
  loop this one for the life of the call.

---

## Android

### Build

```bash
cd android
./gradlew installDebug          # or open the android/ folder in Android Studio
```

The Gradle wrapper JAR is not checked in. Either open the project in Android Studio (which
generates it), or run `gradle wrapper` once with a local Gradle 8.9+.

AGP 8.7.2 · Kotlin 2.0.21 · compileSdk/targetSdk 35 · minSdk 24 · JVM target 17.

### Architecture

```
MainActivity          control panel: trigger now / schedule / cancel / permissions
CallScheduler         setAlarmClock → CallReceiver (use case 2)
CallReceiver          alarm trigger + notification Decline action
BootReceiver          re-arms the alarm after reboot / app update
CallService           phoneCall foreground service: owns the notification, audio, timeout
NotificationHelper    silent channel + CallStyle.forIncomingCall notification
RingtonePlayer        looping MediaPlayer + vibration waveform
IncomingCallActivity  full-screen lock-screen call UI (use case 3)
Permissions           POST_NOTIFICATIONS / USE_FULL_SCREEN_INTENT / SCHEDULE_EXACT_ALARM
Prefs, CallState      scheduled-time persistence, in-process UI state
```

### Four Android design decisions worth knowing

**1. The notification channel is silent, deliberately.** A channel's sound is **immutable once
the channel exists** — calling `createNotificationChannel()` again with a different `Uri` is a
silent no-op, so a custom ringtone set that way only ever works on a fresh install. Channel
sounds also **never loop**. Audio is therefore owned by `RingtonePlayer`, driven by the
foreground service.

**2. Answer is an Activity `PendingIntent`, not a broadcast.** From Android 10, a
`BroadcastReceiver` cannot start an Activity from the background. Answering via a broadcast does
nothing at all on a locked device. Decline stays a broadcast because it needs no UI.

**3. `setAlarmClock`, not `setExact`.** It is the only alarm API exempt from Doze throttling that
*also* grants a short foreground-service-start allowlist when it fires — which is exactly what
`CallReceiver` needs to start a `phoneCall` service from the background.

**4. Exact alarms die on reboot.** `BootReceiver` re-arms from `SharedPreferences` on
`BOOT_COMPLETED` and `MY_PACKAGE_REPLACED`. A trigger time already in the past is dropped rather
than fired late.

### Permissions that the OS can take away

| Permission | Since | What happens without it |
|---|---|---|
| `POST_NOTIFICATIONS` | 13 (API 33) | Nothing shows at all. Requested at first launch. |
| `USE_FULL_SCREEN_INTENT` | **14 (API 34)** — no longer install-granted | Notification still posts, but **does not take over the screen**. `MainActivity` routes to `ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT`. |
| `SCHEDULE_EXACT_ALARM` | 12 (API 31), not pre-granted from 13 | Falls back to an inexact alarm, which Doze can delay by minutes. The UI says so. |

`USE_EXACT_ALARM` is declared alongside `SCHEDULE_EXACT_ALARM` as the pre-granted alternative.
**Keep only one.** Google Play restricts `USE_EXACT_ALARM` to alarm-clock, calendar and calling
apps; shipping it in anything else will fail review.

A `phoneCall` foreground service also requires `MANAGE_OWN_CALLS` on Android 14+, which is
declared. If you are not actually a calling app, change
`android:foregroundServiceType="phoneCall"` to `mediaPlayback` and drop `MANAGE_OWN_CALLS`.

### Testing

```bash
# Use case 1 — tap "Ring now".

# Use case 2 — tap "Ring in 10 seconds", then immediately lock the screen.
#              The call should take over the lock screen with the screen off.

# Use case 2 from adb, with the app not running:
adb shell am broadcast -a com.example.localcallstyle.action.INCOMING \
  -n com.example.localcallstyle/.CallReceiver

# Check the foreground service type actually took:
adb shell dumpsys activity services com.example.localcallstyle | grep -i foreground

# Verify full-screen-intent access on Android 14+:
adb shell cmd notification allow_fsi_permission com.example.localcallstyle   # grant for testing
```

Reboot persistence: schedule a ring far enough out, reboot, confirm it still fires.

---

## iOS

### Build

```bash
brew install xcodegen
cd ios
xcodegen generate
open LocalCallStyle.xcodeproj
```

The project is defined by `ios/project.yml` rather than a checked-in `.xcodeproj`, so there is no
`project.pbxproj` to merge-conflict over. iOS 17 deployment target, Swift 5.10.

In Xcode, under **Signing & Capabilities**, add:

* **Time Sensitive Notifications** — without it, `interruptionLevel = .timeSensitive` is silently
  downgraded to `.active` and the call will not break through Focus.
* **Background Modes → Voice over IP** and **Audio** — already in the generated `Info.plist`;
  the capability makes the provisioning profile carry them.

### Architecture

```
LocalCallStyleApp       SwiftUI entry point; overlays IncomingCallView while ringing
AppDelegate             UNUserNotificationCenterDelegate — handles Answer / Decline
ContentView             control panel, permission state, ringtone-bundled check
IncomingCallView        in-app call screen (use case 3)
CallNotificationManager local notifications: categories, chained ring pulses, cancel
CallKitManager          CXProvider — the real system call UI; PushKit hook documented
CallState               observable phase (idle / scheduled / ringing / answered / declined)
CallIntents             shared identifiers and timings
```

### Two iOS design decisions worth knowing

**1. Ringing is a chain of notifications.** `UNNotificationSound` plays once; there is no
`isLooping`. `scheduleCall` posts nine notifications 5 s apart under one `threadIdentifier` (so
the lock screen shows one call, not a stack), and cancels the remainder the instant the user
answers or declines.

**2. Answer is `.foreground`, Decline is not.** Answering needs the app up to show the in-call UI;
declining is handled in the background with no launch.

### Ringing through Silent mode

Time-sensitive notifications break through **Focus**, but not the **hardware mute switch**. For
that you need `interruptionLevel = .critical`, which requires the **Critical Alerts** entitlement
— granted by Apple on request only, normally for medical, home-safety and public-safety apps:
<https://developer.apple.com/contact/request/notifications-critical-alerts>

### Testing

```
Use case 1 — tap "Ring now" with the app open. You should get the real iOS call screen
             (CallKit), not a banner.

Use case 2 — tap "Ring in 10 seconds", then swipe the app away to terminate it and lock
             the phone. You should get a time-sensitive notification with Answer / Decline.
             This is a lock-screen notification, NOT a full-screen takeover — see the
             platform note at the top.

Use case 3 — Answer and Decline from the notification, from the CallKit screen, and from
             the in-app screen. All three paths cancel the remaining ring pulses.
```

The Simulator does not play notification sounds reliably and CallKit behaves differently there.
Test on a device.

---

## Repository layout

```
localcall/
├── README.md
├── scripts/
│   └── make-ringtone.sh            mp3 → android mp3 + ios caf
├── android/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   ├── gradle.properties
│   ├── gradle/wrapper/gradle-wrapper.properties
│   └── app/
│       ├── build.gradle.kts
│       ├── proguard-rules.pro
│       └── src/main/
│           ├── AndroidManifest.xml
│           ├── java/com/example/localcallstyle/   (11 Kotlin files)
│           └── res/
│               ├── layout/, values/, drawable/, xml/
│               └── raw/README.txt                 ← drop ringtone.mp3 here
└── ios/
    ├── project.yml                 XcodeGen spec
    ├── Sources/                    (8 Swift files)
    └── Resources/
        ├── Info.plist
        ├── LocalCallStyle.entitlements
        └── ringtone-README.txt     ← why MP3 does not work here
```

## Notes on the original snippet this was built from

Fixed along the way, in case the same code is in use elsewhere:

* `importimport android.content.Context` in `MainActivity.kt` — a hard syntax error.
* Manifest `xmlns:android="http://android.com"` — must be
  `http://schemas.android.com/apk/res/android`, otherwise nothing in the manifest resolves.
* Manifest `package=` is deprecated under AGP 8 — replaced by `namespace` in
  `app/build.gradle.kts`.
* `setAutoCancel(true)` together with `setOngoing(true)` — contradictory for a ringing call.
* Full-screen `PendingIntent` used `FLAG_MUTABLE` — should be `FLAG_IMMUTABLE` (required on
  API 23+, and lint-flagged for full-screen intents).
* `createNotificationChannel()` called on every notification to change the sound — a no-op after
  first install, and channel sounds do not loop. This silently defeats the custom-ringtone goal.
* Answer action delivered as a broadcast — cannot start an Activity on Android 10+.
* No handling of Android 14's revoked `USE_FULL_SCREEN_INTENT` or non-pre-granted
  `SCHEDULE_EXACT_ALARM`.
* No `FOREGROUND_SERVICE` / `FOREGROUND_SERVICE_PHONE_CALL` / `MANAGE_OWN_CALLS`, so the
  `phoneCall` service could not start on Android 14.
* No reboot persistence for the scheduled alarm.
