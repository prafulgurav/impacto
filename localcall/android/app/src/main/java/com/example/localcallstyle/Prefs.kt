package com.example.localcallstyle

import android.content.Context
import android.content.SharedPreferences

/**
 * Exact alarms do not survive a reboot or an app update, so the scheduled trigger time is
 * persisted here and re-armed by [BootReceiver].
 */
object Prefs {

    private const val NAME = "localcallstyle.prefs"
    private const val KEY_SCHEDULED_AT = "scheduled_at"
    private const val KEY_CALLER = "scheduled_caller"

    private fun prefs(context: Context): SharedPreferences =
        context.applicationContext.getSharedPreferences(NAME, Context.MODE_PRIVATE)

    fun saveScheduledCall(context: Context, triggerAtMillis: Long, callerName: String) {
        prefs(context).edit()
            .putLong(KEY_SCHEDULED_AT, triggerAtMillis)
            .putString(KEY_CALLER, callerName)
            .apply()
    }

    fun clearScheduledCall(context: Context) {
        prefs(context).edit()
            .remove(KEY_SCHEDULED_AT)
            .remove(KEY_CALLER)
            .apply()
    }

    /** @return the epoch-millis trigger time, or 0 if nothing is scheduled. */
    fun scheduledAt(context: Context): Long = prefs(context).getLong(KEY_SCHEDULED_AT, 0L)

    fun scheduledCaller(context: Context): String? = prefs(context).getString(KEY_CALLER, null)
}
