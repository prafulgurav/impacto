package com.example.localcallstyle

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

/**
 * Owns the lifetime of one ringing call: the ongoing CallStyle notification, the looping
 * ringtone, and the ring timeout.
 *
 * It runs as a `phoneCall` foreground service because that is the only way to keep looping audio
 * alive while the app is in the background, and because CallStyle notifications are designed to
 * be attached to one.
 */
class CallService : Service() {

    private val timeoutHandler = Handler(Looper.getMainLooper())
    private val timeoutRunnable = Runnable {
        Log.i(TAG, "Ring timed out after ${CallIntents.RING_TIMEOUT_MS} ms")
        CallState.markMissed()
        stopEverything()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            CallIntents.ACTION_INCOMING -> startRinging(
                intent.getStringExtra(CallIntents.EXTRA_CALLER_NAME)
                    ?: getString(R.string.caller_name)
            )

            CallIntents.ACTION_ANSWER -> {
                CallState.markAnswered()
                stopEverything()
            }

            CallIntents.ACTION_DECLINE -> {
                CallState.markDeclined()
                stopEverything()
            }

            else -> stopEverything()
        }
        return START_NOT_STICKY
    }

    private fun startRinging(callerName: String) {
        // startForeground must happen within ~10 s of the service being started, and before any
        // long work, or the system throws.
        val notification = NotificationHelper.buildIncomingCall(this, callerName)
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ServiceCompat.startForeground(
                    this,
                    CallIntents.CALL_NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_PHONE_CALL
                )
            } else {
                startForeground(CallIntents.CALL_NOTIFICATION_ID, notification)
            }
        } catch (e: Exception) {
            // On Android 12+ a background start can be rejected outright
            // (ForegroundServiceStartNotAllowedException). Nothing to ring if so.
            Log.e(TAG, "Could not enter the foreground; aborting the call", e)
            stopSelf()
            return
        }

        CallState.markRinging(callerName)
        RingtonePlayer.start(this)

        timeoutHandler.removeCallbacks(timeoutRunnable)
        timeoutHandler.postDelayed(timeoutRunnable, CallIntents.RING_TIMEOUT_MS)
    }

    private fun stopEverything() {
        timeoutHandler.removeCallbacks(timeoutRunnable)
        RingtonePlayer.stop()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        NotificationHelper.cancel(this)
        stopSelf()
    }

    override fun onDestroy() {
        timeoutHandler.removeCallbacks(timeoutRunnable)
        RingtonePlayer.stop()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "CallService"

        fun startIncoming(context: Context, callerName: String) {
            val intent = Intent(context, CallService::class.java).apply {
                action = CallIntents.ACTION_INCOMING
                putExtra(CallIntents.EXTRA_CALLER_NAME, callerName)
            }
            ContextCompat.startForegroundService(context, intent)
        }

        fun answer(context: Context) = send(context, CallIntents.ACTION_ANSWER)

        fun decline(context: Context) = send(context, CallIntents.ACTION_DECLINE)

        fun stop(context: Context) = send(context, CallIntents.ACTION_STOP)

        private fun send(context: Context, action: String) {
            val intent = Intent(context, CallService::class.java).apply { this.action = action }
            try {
                // The service is already in the foreground at this point, so a plain start is
                // enough and avoids the "started as foreground but never called
                // startForeground" crash for the stop path.
                context.startService(intent)
            } catch (e: Exception) {
                Log.w(TAG, "Could not deliver $action", e)
                // Service already gone: make sure nothing is left ringing.
                RingtonePlayer.stop()
                NotificationHelper.cancel(context)
            }
        }
    }
}
