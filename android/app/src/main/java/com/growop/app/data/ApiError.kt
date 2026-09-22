package com.growop.app.data

import java.io.IOException
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.net.UnknownServiceException
import javax.net.ssl.SSLException

/** Every failure the UI can show. `message` is always plain language. */
sealed class ApiError(override val message: String) : Exception(message) {
    object NotConfigured : ApiError("The app isn't connected to your grow brain yet. Open Settings to set it up.")
    class InvalidUrl(s: String) : ApiError("\"$s\" doesn't look like a valid address.")
    object Unauthorized : ApiError("The grow brain rejected the API key. Check it in Settings.")
    class Http(val status: Int, val detail: String?) :
        ApiError(if (!detail.isNullOrBlank()) detail else "The server replied with an error ($status).")
    class Network(val cause0: Throwable) : ApiError(describe(cause0))
    class Decoding(val cause0: Throwable) :
        ApiError("The server sent something the app didn't understand. (${cause0.message ?: cause0::class.simpleName})")
    class Other(val cause0: Throwable) : ApiError(cause0.message ?: "Something went wrong.")

    // Home Assistant (ingress) mode
    object HaTokenRejected : ApiError(
        "Home Assistant rejected the access token. Create a new one in Home Assistant (your profile → Security → Create token), copy ALL of it (about 180 characters), and paste it in. The Grow Brain API key is separate and goes in the \"Grow Brain API key\" field."
    )
    class HaTokenMalformed(n: Int) : ApiError(
        "That doesn't look like a Home Assistant long-lived access token ($n characters; a real one is about 180 characters with two dots). Create one under your profile → Security → Create token and copy the whole thing."
    )
    object HaNotAdmin : ApiError("That Home Assistant account isn't an administrator, so it can't reach add-ons. Make a token from an admin account.")
    object HaAddonNotFound : ApiError("Grow Brain add-on not found in Home Assistant. Make sure it's installed and running.")
    class HaIngressSessionFailed(why: String) :
        ApiError("Ingress session failed: Home Assistant wouldn't open a session for the add-on. $why")
    class HaError(val status: Int, val detail: String?) : ApiError(
        when {
            !detail.isNullOrBlank() && status > 0 -> "Home Assistant replied: $detail ($status)"
            !detail.isNullOrBlank() -> "Home Assistant replied: $detail"
            status == 404 -> "Home Assistant replied 404. This needs a Home Assistant OS or Supervised install with the Grow Brain add-on."
            else -> "Home Assistant replied with an error ($status)."
        }
    )
    /** The WebSocket to Home Assistant (used for add-on discovery and ingress sessions) could not be used. */
    class HaWebSocketFailed(host: String, why: String) : ApiError(
        "Couldn't talk to Home Assistant at $host over its WebSocket API: $why If the address is right, check that Home Assistant is reachable from this phone and that the token is a long-lived access token from an admin account."
    )
    /** Wraps an error with the name of the connection step that failed. */
    class Step(val step: String, val inner: Throwable) : ApiError("$step: ${inner.message}")

    companion object {
        fun describe(e: Throwable): String = when (e) {
            is SocketTimeoutException -> "The server took too long to respond. Try again in a moment."
            is UnknownHostException -> "Can't find that address. If it ends in .local, try the server's IP address instead (for example http://192.168.1.50:8099)."
            is ConnectException, is NoRouteToHostException -> "Nothing answered at that address. Check the address and port, that the phone is on the home Wi‑Fi, and that the Grow Brain add-on is running."
            is UnknownServiceException -> if ((e.message ?: "").contains("CLEARTEXT", ignoreCase = true))
                "Plain http:// traffic was blocked on this phone. Check the address, or use \"Through Home Assistant\" with an https:// address."
            else "Network problem: ${e.message}"
            is SSLException -> "Secure connection failed. For a Nabu Casa address this almost always means a typo in the long name: paste it from Home Assistant → Settings → Home Assistant Cloud instead of typing it. For a Same Wi‑Fi address, use http:// not https://."
            is IOException -> {
                val m = e.message ?: ""
                when {
                    m.contains("Cleartext", true) -> "Plain http:// traffic was blocked on this phone. Check the address, or use \"Through Home Assistant\" with an https:// address."
                    m.contains("reset", true) || m.contains("unexpected end of stream", true) ->
                        "The connection was reset. Usual causes: a VPN on this phone (turn it off), or the address starting with https:// instead of http://."
                    m.contains("Network is unreachable", true) || m.contains("ENETUNREACH", true) ->
                        "No network connection. Check Wi‑Fi."
                    m.isNotBlank() -> "Network problem: $m"
                    else -> "Network problem (${e::class.simpleName})."
                }
            }
            else -> e.message ?: "Something went wrong (${e::class.simpleName})."
        }

        /** Normalises any throwable into an ApiError. */
        fun wrap(e: Throwable): ApiError = when (e) {
            is ApiError -> e
            is IOException -> Network(e)
            else -> Other(e)
        }
    }
}
