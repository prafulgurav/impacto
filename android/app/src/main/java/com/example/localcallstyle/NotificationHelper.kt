package com.example.localcallstyle

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.Person

object NotificationHelper {

    const val CHANNEL_ID = "incoming_calls_v1"

    /**
     * The channel is deliberately **silent** with vibration off.
     *
     * A channel's sound and vibration cannot be changed once it exists, and channel sounds never
     * loop — so sound here would both fight [RingtonePlayer] and be impossible to customise after
     * first install. Audio is the foreground service's job.
     *
     * Idempotent: safe to call on every app start.
     */
    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java) ?: return

        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.notif_channel_name),
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = context.getString(R.string.notif_channel_desc)
            setSound(null, null)
            enableVibration(false)
            lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            setShowBadge(false)
            setBypassDnd(true)
        }
        manager.createNotificationChannel(channel)
    }

    fun buildIncomingCall(context: Context, callerName: String): android.app.Notification {
        val caller: Person = Person.Builder()
            .setName(callerName)
            .setImportant(true)
            .build()

        // Answer MUST be an Activity PendingIntent. From Android 10 a BroadcastReceiver cannot
        // start an Activity from the background, so answering via a broadcast silently does
        // nothing on a locked device.
        val answerIntent = PendingIntent.getActivity(
            context,
            CallIntents.RC_ANSWER,
            Intent(context, IncomingCallActivity::class.java).apply {
                action = CallIntents.ACTION_ANSWER
                putExtra(CallIntents.EXTRA_CALLER_NAME, callerName)
                putExtra(CallIntents.EXTRA_AUTO_ANSWER, true)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Decline needs no UI, so a broadcast is the cheapest correct choice.
        val declineIntent = PendingIntent.getBroadcast(
            context,
            CallIntents.RC_DECLINE,
            Intent(context, CallReceiver::class.java).apply {
                action = CallIntents.ACTION_DECLINE
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // The full-screen intent is what turns the screen on and takes over the lock screen.
        // FLAG_IMMUTABLE is required on API 23+ and is correct here — the system never needs to
        // fill anything in.
        val fullScreenIntent = PendingIntent.getActivity(
            context,
            CallIntents.RC_FULL_SCREEN,
            Intent(context, IncomingCallActivity::class.java).apply {
                action = CallIntents.ACTION_INCOMING
                putExtra(CallIntents.EXTRA_CALLER_NAME, callerName)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_call)
            .setContentTitle(callerName)
            .setContentText(context.getString(R.string.caller_subtitle))
            .setStyle(
                NotificationCompat.CallStyle.forIncomingCall(caller, declineIntent, answerIntent)
            )
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            // Ongoing + not auto-cancel: a ringing call must not be swipeable away, and
            // setAutoCancel(true) alongside setOngoing(true) is contradictory.
            .setOngoing(true)
            .setAutoCancel(false)
            .setOnlyAlertOnce(true)
            // Silent at the notification level too — RingtonePlayer owns sound and vibration.
            .setSilent(true)
            .setFullScreenIntent(fullScreenIntent, true)
            .setContentIntent(fullScreenIntent)
            .setTimeoutAfter(CallIntents.RING_TIMEOUT_MS)
            .build()
    }

    fun cancel(context: Context) {
        NotificationManagerCompat.from(context).cancel(CallIntents.CALL_NOTIFICATION_ID)
    }
}
