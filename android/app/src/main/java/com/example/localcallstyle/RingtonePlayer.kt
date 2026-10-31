package com.example.localcallstyle

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import androidx.core.content.getSystemService

/**
 * Plays the ringtone in a loop for as long as the call is up.
 *
 * Why this is not done with a notification channel sound:
 *  1. A channel's sound is **immutable after the channel is created**. Calling
 *     createNotificationChannel() again with a different Uri is silently a no-op, so a custom
 *     ringtone set that way only ever works on a fresh install.
 *  2. Channel sounds **do not loop**. A ringtone that plays once for four seconds is not a
 *     ringtone.
 *
 * So the channel is created silent (see [NotificationHelper]) and audio is owned here, driven by
 * the phoneCall foreground service.
 *
 * ## Custom ringtone
 * Drop an audio file at `app/src/main/res/raw/ringtone.mp3` and it is picked up automatically —
 * the resource is looked up by name at runtime so the project still compiles without one.
 * `.mp3`, `.ogg`, `.m4a` and `.wav` all work; if you use a different extension, change
 * [RINGTONE_RES_NAME] only (the name, never the extension).
 */
object RingtonePlayer {

    private const val TAG = "RingtonePlayer"

    /** Base name of the file in res/raw, without extension. */
    private const val RINGTONE_RES_NAME = "ringtone"

    private var player: MediaPlayer? = null
    private var vibrator: Vibrator? = null

    /** True when a bundled custom ringtone was found; surfaced in the UI for clarity. */
    fun hasCustomRingtone(context: Context): Boolean = customRingtoneResId(context) != 0

    private fun customRingtoneResId(context: Context): Int =
        context.resources.getIdentifier(RINGTONE_RES_NAME, "raw", context.packageName)

    @Synchronized
    fun start(context: Context) {
        stop() // never stack two players

        val audioManager = context.getSystemService<AudioManager>()
        val ringerMode = audioManager?.ringerMode ?: AudioManager.RINGER_MODE_NORMAL

        if (ringerMode == AudioManager.RINGER_MODE_NORMAL) {
            startAudio(context)
        }
        if (ringerMode != AudioManager.RINGER_MODE_SILENT) {
            startVibration(context)
        }
    }

    private fun startAudio(context: Context) {
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()

        val resId = customRingtoneResId(context)
        try {
            player = MediaPlayer().apply {
                setAudioAttributes(attributes)
                isLooping = true
                if (resId != 0) {
                    context.resources.openRawResourceFd(resId).use { afd ->
                        setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
                    }
                } else {
                    val fallback: Uri =
                        RingtoneManager.getActualDefaultRingtoneUri(context, RingtoneManager.TYPE_RINGTONE)
                            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
                    setDataSource(context, fallback)
                }
                setOnErrorListener { _, what, extra ->
                    Log.w(TAG, "MediaPlayer error what=$what extra=$extra")
                    stop()
                    true
                }
                prepare()
                start()
            }
        } catch (e: Exception) {
            // A corrupt or unsupported audio file must not take the call down with it.
            Log.e(TAG, "Unable to start ringtone", e)
            releasePlayer()
        }
    }

    private fun startVibration(context: Context) {
        val vib: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService<VibratorManager>()?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService<Vibrator>()
        }
        if (vib == null || !vib.hasVibrator()) return
        vibrator = vib

        // wait, buzz, wait — repeating from index 0 gives a telephone-like cadence.
        val timings = longArrayOf(0, 1000, 1000)

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val amplitudes = intArrayOf(0, VibrationEffect.DEFAULT_AMPLITUDE, 0)
                vib.vibrate(VibrationEffect.createWaveform(timings, amplitudes, 0))
            } else {
                @Suppress("DEPRECATION")
                vib.vibrate(timings, 0)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Unable to vibrate", e)
        }
    }

    @Synchronized
    fun stop() {
        releasePlayer()
        try {
            vibrator?.cancel()
        } catch (e: Exception) {
            Log.w(TAG, "Unable to cancel vibration", e)
        }
        vibrator = null
    }

    private fun releasePlayer() {
        player?.let {
            try {
                if (it.isPlaying) it.stop()
            } catch (_: IllegalStateException) {
                // already stopped
            }
            it.release()
        }
        player = null
    }
}
