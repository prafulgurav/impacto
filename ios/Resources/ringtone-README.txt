iOS custom ringtone — read this before you drop in an .mp3
==========================================================

MP3 IS NOT A VALID NOTIFICATION SOUND ON iOS.

UNNotificationSound accepts only:

    .caf   (Core Audio Format)  <- recommended
    .aiff
    .wav

and the file must be 30 SECONDS OR SHORTER. An unsupported format or an
over-long file does not raise an error: iOS silently plays the default
notification sound instead, which is the single most common reason a
"custom sound isn't working" on iOS.

Convert your mp3 with the helper script in the repo:

    ../scripts/make-ringtone.sh ~/Downloads/my-ring.mp3

It writes `ringtone.caf` into this directory, trimmed to 29 seconds.

Then make sure the file is in the target's "Copy Bundle Resources" phase
(XcodeGen does this automatically for everything under Resources/).

Two separate sounds, two separate rules
---------------------------------------

1. NOTIFICATION sound (CallNotificationManager)
   - file: Resources/ringtone.caf
   - formats: caf / aiff / wav, <= 30 s
   - referenced by name:  UNNotificationSound(named: "ringtone.caf")
   - does NOT loop; the app chains several notifications to keep ringing.

2. CALLKIT ringtone (CallKitManager)
   - file: Resources/ringtone.caf (the same file is fine)
   - set via CXProviderConfiguration.ringtoneSound = "ringtone.caf"
   - CallKit DOES loop this one for the life of the call.
   - only applies when the call is reported through CallKit, which needs the
     app to be running (or a PushKit VoIP push — see the top-level README).

Critical sounds
---------------
To ring through Silent mode and Focus you need interruptionLevel = .critical,
which requires the "Critical Alerts" entitlement. That is granted by Apple on
request only (https://developer.apple.com/contact/request/notifications-critical-alerts)
and is normally approved for medical, home-safety and public-safety apps.
Without it, a time-sensitive notification breaks through Focus but not the
hardware mute switch.
