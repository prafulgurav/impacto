package com.example.localcallstyle

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Use cases 1 and 3: receives the alarm trigger and the notification's Decline action.
 *
 * Note what this receiver deliberately does **not** do: start an Activity. From Android 10,
 * background activity starts from a receiver are blocked, so the full-screen call UI is launched
 * by the notification's full-screen intent (and by the Answer action, which is an Activity
 * PendingIntent) rather than from here.
 */
class CallReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            CallIntents.ACTION_INCOMING -> {
                val caller = intent.getStringExtra(CallIntents.EXTRA_CALLER_NAME)
                    ?: Prefs.scheduledCaller(context)
                    ?: context.getString(R.string.caller_name)

                // The alarm has fired, so this scheduled call is spent.
                Prefs.clearScheduledCall(context)

                NotificationHelper.ensureChannel(context)
                CallService.startIncoming(context, caller)
            }

            CallIntents.ACTION_DECLINE -> CallService.decline(context)

            CallIntents.ACTION_STOP -> CallService.stop(context)

            else -> Log.w(TAG, "Ignoring unexpected action: ${intent.action}")
        }
    }

    private companion object {
        const val TAG = "CallReceiver"
    }
}
