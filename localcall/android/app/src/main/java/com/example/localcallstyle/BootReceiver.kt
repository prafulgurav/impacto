package com.example.localcallstyle

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Pending exact alarms are cleared when the device reboots or the app is replaced. Without this,
 * a scheduled call silently never arrives.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED -> {
                NotificationHelper.ensureChannel(context)
                CallScheduler.restoreAfterBoot(context)
            }
        }
    }
}
