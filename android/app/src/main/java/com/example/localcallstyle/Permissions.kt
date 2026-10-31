package com.example.localcallstyle

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.ContextCompat
import androidx.core.content.getSystemService

/**
 * Everything the OS can take away from us at runtime.
 *
 * The three that matter, and the versions where they changed:
 *  - POST_NOTIFICATIONS       runtime permission from Android 13 (API 33).
 *  - USE_FULL_SCREEN_INTENT   no longer granted at install time from Android 14 (API 34) for
 *                             apps that are not default dialers/alarm clocks. Without it the
 *                             notification still posts, but it will not take over the screen.
 *  - SCHEDULE_EXACT_ALARM     user-revocable from Android 12 (API 31) and not pre-granted from
 *                             Android 13. USE_EXACT_ALARM is pre-granted instead but Google Play
 *                             only allows it for alarm clock / calendar / calling apps.
 */
object Permissions {

    fun hasPostNotifications(context: Context): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            true
        } else {
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        }

    fun canUseFullScreenIntent(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return true
        val nm = context.getSystemService<NotificationManager>() ?: return false
        return nm.canUseFullScreenIntent()
    }

    fun canScheduleExactAlarms(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        val am = context.getSystemService<AlarmManager>() ?: return false
        return am.canScheduleExactAlarms()
    }

    /** Settings screen that grants full-screen-intent access. Null below Android 14. */
    fun fullScreenIntentSettings(context: Context): Intent? =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            null
        } else {
            Intent(
                Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT,
                Uri.fromParts("package", context.packageName, null)
            )
        }

    /** Settings screen that grants exact-alarm access. Null below Android 12. */
    fun exactAlarmSettings(context: Context): Intent? =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            null
        } else {
            Intent(
                Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                Uri.fromParts("package", context.packageName, null)
            )
        }

    fun appNotificationSettings(context: Context): Intent =
        Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
}
