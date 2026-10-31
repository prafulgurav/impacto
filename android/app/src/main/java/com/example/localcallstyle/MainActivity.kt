package com.example.localcallstyle

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.text.format.DateFormat
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import java.util.Date

/**
 * Control panel for the three use cases.
 *
 *  1. Ring now           — starts the phoneCall service immediately.
 *  2. Ring in 10 seconds — arms an alarm; works with the app closed or the screen off.
 *  3. Answer / Decline   — handled by the notification actions and the full-screen UI.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var permissionText: TextView
    private lateinit var ringtoneText: TextView

    private val requestNotifications =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (!granted) {
                Toast.makeText(this, R.string.perm_notifications_rationale, Toast.LENGTH_LONG).show()
            }
            refreshPermissionState()
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        NotificationHelper.ensureChannel(this)

        statusText = findViewById(R.id.statusText)
        permissionText = findViewById(R.id.permissionText)
        ringtoneText = findViewById(R.id.ringtoneText)

        findViewById<Button>(R.id.btnTriggerNow).setOnClickListener { triggerNow() }
        findViewById<Button>(R.id.btnSchedule).setOnClickListener { scheduleIn(10_000L) }
        findViewById<Button>(R.id.btnCancelScheduled).setOnClickListener { cancelScheduled() }
        findViewById<Button>(R.id.btnStop).setOnClickListener { CallService.stop(this) }
        findViewById<Button>(R.id.btnPermissions).setOnClickListener { requestMissingPermissions() }

        CallState.current.observe(this) { snapshot ->
            statusText.text = when (snapshot.phase) {
                CallState.Phase.IDLE -> getString(R.string.status_idle)
                CallState.Phase.RINGING -> getString(R.string.notif_channel_name)
                CallState.Phase.ANSWERED -> getString(R.string.status_answered)
                CallState.Phase.DECLINED -> getString(R.string.status_declined)
                CallState.Phase.MISSED -> getString(R.string.status_idle)
            }
        }

        ringtoneText.text = if (RingtonePlayer.hasCustomRingtone(this)) {
            "Custom ringtone: res/raw/ringtone.mp3"
        } else {
            getString(R.string.ringtone_missing)
        }

        askForNotificationsIfNeeded()
    }

    override fun onResume() {
        super.onResume()
        refreshPermissionState()
        showScheduledTimeIfAny()
    }

    private fun askForNotificationsIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            !Permissions.hasPostNotifications(this)
        ) {
            requestNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private fun triggerNow() {
        if (!Permissions.hasPostNotifications(this)) {
            askForNotificationsIfNeeded()
            return
        }
        CallService.startIncoming(this, getString(R.string.caller_name))
    }

    private fun scheduleIn(delayMillis: Long) {
        if (!Permissions.hasPostNotifications(this)) {
            askForNotificationsIfNeeded()
            return
        }
        val triggerAt = CallScheduler.schedule(this, delayMillis, getString(R.string.caller_name))
        if (triggerAt == null) {
            Toast.makeText(this, R.string.perm_exact_alarm_missing, Toast.LENGTH_LONG).show()
            return
        }
        showScheduledTimeIfAny()
        Toast.makeText(this, R.string.btn_schedule, Toast.LENGTH_SHORT).show()
    }

    private fun cancelScheduled() {
        CallScheduler.cancel(this)
        statusText.text = getString(R.string.status_cancelled)
    }

    private fun showScheduledTimeIfAny() {
        val at = Prefs.scheduledAt(this)
        if (at > 0L) {
            val formatted = DateFormat.getTimeFormat(this).format(Date(at))
            statusText.text = getString(R.string.status_scheduled, formatted)
        }
    }

    /** Lists only what is actually missing, and routes to the exact settings page for each. */
    private fun refreshPermissionState() {
        val problems = buildList {
            if (!Permissions.hasPostNotifications(this@MainActivity)) {
                add(getString(R.string.perm_notifications_rationale))
            }
            if (!Permissions.canUseFullScreenIntent(this@MainActivity)) {
                add(getString(R.string.perm_fsi_missing))
            }
            if (!Permissions.canScheduleExactAlarms(this@MainActivity)) {
                add(getString(R.string.perm_exact_alarm_missing))
            }
        }

        if (problems.isEmpty()) {
            permissionText.text = getString(R.string.perm_all_granted)
            permissionText.visibility = View.VISIBLE
        } else {
            permissionText.text = problems.joinToString("\n\n• ", prefix = "• ")
            permissionText.visibility = View.VISIBLE
        }
    }

    private fun requestMissingPermissions() {
        if (!Permissions.hasPostNotifications(this)) {
            askForNotificationsIfNeeded()
            return
        }
        if (!Permissions.canUseFullScreenIntent(this)) {
            startSettings(Permissions.fullScreenIntentSettings(this))
            return
        }
        if (!Permissions.canScheduleExactAlarms(this)) {
            startSettings(Permissions.exactAlarmSettings(this))
            return
        }
        startSettings(Permissions.appNotificationSettings(this))
    }

    private fun startSettings(intent: Intent?) {
        if (intent == null) return
        try {
            startActivity(intent)
        } catch (_: Exception) {
            // Some OEM builds do not ship these screens; fall back to app notification settings.
            try {
                startActivity(Permissions.appNotificationSettings(this))
            } catch (_: Exception) {
                Toast.makeText(this, R.string.perm_all_granted, Toast.LENGTH_SHORT).show()
            }
        }
    }
}
