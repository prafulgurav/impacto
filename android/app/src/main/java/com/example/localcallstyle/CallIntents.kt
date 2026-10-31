package com.example.localcallstyle

/**
 * Single source of truth for the intent plumbing. Keeping these in one place avoids the
 * classic bug where the notification action and the receiver disagree on a string.
 */
object CallIntents {

    private const val PREFIX = "com.example.localcallstyle.action."

    /** Fired by the alarm, or by MainActivity, to begin a (fake) incoming call. */
    const val ACTION_INCOMING = PREFIX + "INCOMING"

    /** User tapped Answer — on the notification or on the full-screen UI. */
    const val ACTION_ANSWER = PREFIX + "ANSWER"

    /** User tapped Decline. */
    const val ACTION_DECLINE = PREFIX + "DECLINE"

    /** Internal: stop ringing without recording an answer/decline (timeout, app teardown). */
    const val ACTION_STOP = PREFIX + "STOP"

    const val EXTRA_CALLER_NAME = "com.example.localcallstyle.extra.CALLER_NAME"

    /** Set when IncomingCallActivity is launched by the notification's Answer action. */
    const val EXTRA_AUTO_ANSWER = "com.example.localcallstyle.extra.AUTO_ANSWER"

    /** Notification id for the single in-flight call. */
    const val CALL_NOTIFICATION_ID = 1001

    /** Distinct PendingIntent request codes — reusing one would clobber the other intents. */
    const val RC_FULL_SCREEN = 10
    const val RC_ANSWER = 11
    const val RC_DECLINE = 12
    const val RC_ALARM = 13
    const val RC_CONTENT = 14

    /** How long the call rings before it gives up, in milliseconds. */
    const val RING_TIMEOUT_MS = 45_000L
}
