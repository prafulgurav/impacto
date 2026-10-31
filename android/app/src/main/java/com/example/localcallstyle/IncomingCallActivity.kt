package com.example.localcallstyle

import android.app.KeyguardManager
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import android.widget.ImageButton
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.getSystemService

/**
 * The full-screen "incoming call" UI.
 *
 * Reached three ways:
 *  - the notification's full-screen intent (screen off / locked),
 *  - the notification's Answer action (with [CallIntents.EXTRA_AUTO_ANSWER]),
 *  - tapping the notification body.
 *
 * `showWhenLocked` / `turnScreenOn` are declared in the manifest *and* set here: the manifest
 * attributes cover the cold-start case, the runtime calls cover re-use of an existing instance.
 */
class IncomingCallActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showOverLockScreen()
        setContentView(R.layout.activity_incoming_call)

        val callerName = intent.getStringExtra(CallIntents.EXTRA_CALLER_NAME)
            ?: getString(R.string.caller_name)
        findViewById<TextView>(R.id.callerName).text = callerName

        findViewById<ImageButton>(R.id.btnAnswer).setOnClickListener { answer() }
        findViewById<ImageButton>(R.id.btnDecline).setOnClickListener { decline() }

        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent) {
        // Tapping Answer on the notification should not make the user tap Answer again.
        if (intent.getBooleanExtra(CallIntents.EXTRA_AUTO_ANSWER, false)) {
            answer()
        }
    }

    private fun showOverLockScreen() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                    WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            )
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Ask the system to take down the keyguard. On a secured lock screen this prompts the
        // user rather than bypassing it — which is the correct behaviour.
        getSystemService<KeyguardManager>()?.requestDismissKeyguard(this, null)
    }

    private fun answer() {
        CallService.answer(this)
        // A real app would open its in-call screen here. This demo has nothing to show, so it
        // hands control back to the control panel.
        startActivity(
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        )
        finish()
    }

    private fun decline() {
        CallService.decline(this)
        finish()
    }
}
