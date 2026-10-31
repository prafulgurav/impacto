package com.example.localcallstyle

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.content.getSystemService

/**
 * Use case 2: the alarm-style trigger.
 *
 * `setAlarmClock` is used rather than `setExactAndAllowWhileIdle` because it is the only API that
 * is exempt from Doze throttling *and* grants a short foreground-service start allowlist when it
 * fires — which is exactly what [CallReceiver] needs in order to start the phoneCall service from
 * the background.
 */
object CallScheduler {

    private const val TAG = "CallScheduler"

    private fun pendingIntent(context: Context): PendingIntent =
        PendingIntent.getBroadcast(
            context,
            CallIntents.RC_ALARM,
            Intent(context, CallReceiver::class.java).apply {
                action = CallIntents.ACTION_INCOMING
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

    /**
     * @return the epoch-millis time the call will ring, or null if the OS refused the alarm
     *         (exact-alarm permission revoked).
     */
    fun schedule(context: Context, delayMillis: Long, callerName: String): Long? {
        val am = context.getSystemService<AlarmManager>() ?: return null
        val triggerAt = System.currentTimeMillis() + delayMillis
        val operation = pendingIntent(context)

        return try {
            if (Permissions.canScheduleExactAlarms(context)) {
                am.setAlarmClock(AlarmManager.AlarmClockInfo(triggerAt, operation), operation)
            } else {
                // Degrade honestly rather than crash: inexact alarms can be delayed by minutes
                // in Doze, and the UI says so.
                Log.w(TAG, "Exact alarms not permitted; falling back to an inexact alarm")
                am.set(AlarmManager.RTC_WAKEUP, triggerAt, operation)
            }
            Prefs.saveScheduledCall(context, triggerAt, callerName)
            triggerAt
        } catch (e: SecurityException) {
            Log.e(TAG, "Alarm rejected", e)
            null
        }
    }

    fun cancel(context: Context) {
        context.getSystemService<AlarmManager>()?.cancel(pendingIntent(context))
        Prefs.clearScheduledCall(context)
    }

    /**
     * Exact alarms are dropped on reboot and on app update, so re-arm whatever was pending.
     * A trigger time that is already in the past is discarded rather than fired late.
     */
    fun restoreAfterBoot(context: Context) {
        val triggerAt = Prefs.scheduledAt(context)
        if (triggerAt <= 0L) return

        val remaining = triggerAt - System.currentTimeMillis()
        if (remaining <= 0L) {
            Log.i(TAG, "Scheduled call was missed while the device was off; dropping it")
            Prefs.clearScheduledCall(context)
            return
        }
        val caller = Prefs.scheduledCaller(context)
            ?: context.getString(R.string.caller_name)
        schedule(context, remaining, caller)
    }

    @Suppress("unused")
    fun isScheduled(context: Context): Boolean = Prefs.scheduledAt(context) > 0L
}
