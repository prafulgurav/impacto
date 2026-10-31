package com.example.localcallstyle

import androidx.lifecycle.MutableLiveData

/**
 * Tiny in-process state holder so MainActivity can show what happened without a database.
 * Process-scoped on purpose — none of this needs to outlive the app.
 */
object CallState {

    enum class Phase { IDLE, RINGING, ANSWERED, DECLINED, MISSED }

    data class Snapshot(val phase: Phase, val callerName: String?)

    val current = MutableLiveData(Snapshot(Phase.IDLE, null))

    private fun set(phase: Phase, callerName: String? = current.value?.callerName) {
        current.postValue(Snapshot(phase, callerName))
    }

    fun markRinging(callerName: String) = set(Phase.RINGING, callerName)
    fun markAnswered() = set(Phase.ANSWERED)
    fun markDeclined() = set(Phase.DECLINED)
    fun markMissed() = set(Phase.MISSED)
    fun reset() = set(Phase.IDLE, null)
}
