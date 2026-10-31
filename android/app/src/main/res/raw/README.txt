Drop your custom ringtone here.

    app/src/main/res/raw/ringtone.mp3

That's the whole setup. RingtonePlayer looks the resource up by name at runtime
(resources.getIdentifier("ringtone", "raw", packageName)), so:

  * the project compiles whether or not the file is present;
  * with no file, it falls back to the device's default ringtone;
  * .mp3, .ogg, .m4a and .wav all work.

Rules for res/raw file names: lowercase letters, digits and underscores only.
"MyRingtone.mp3" or "ring-tone.mp3" will fail the resource build.

Length does not matter — the file is played on a loop by MediaPlayer, not by the
notification channel, so even a 2-second loop rings continuously until the call
is answered, declined, or times out after 45 seconds.

Keep the file reasonably small (under ~1 MB) so it loads without a gap; a 128 kbps
mono MP3 of 5-10 seconds is ideal.

To use a different file name, change RINGTONE_RES_NAME in RingtonePlayer.kt
(the base name only, never the extension).
