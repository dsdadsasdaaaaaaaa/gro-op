package com.growop.app

import android.content.Context
import com.growop.app.state.AppState

/** Tiny manual DI: one AppState per process. */
class AppContainer(context: Context) {
    val appState: AppState = AppState(context.applicationContext)
}
