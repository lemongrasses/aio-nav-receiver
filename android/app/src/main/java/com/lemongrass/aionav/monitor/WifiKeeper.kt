package com.lemongrass.aionav.monitor

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** What the phone's Wi-Fi is doing, for the Settings screen. */
data class WifiState(
    val connected: Boolean = false,
    /** The Jetson hotspot has no internet; Android then prefers mobile data but keeps Wi-Fi up for us. */
    val noInternet: Boolean = false,
)

/**
 * Keeps the Wi-Fi network up while monitoring. The Jetson hotspot has no internet: Android then moves
 * the default route to mobile data and may drop the Wi-Fi network once nothing needs it. Holding a
 * request for a Wi-Fi network that does not ask for internet keeps it connected (incoming UDP still
 * arrives on the Wi-Fi address; the socket listens on 0.0.0.0).
 */
class WifiKeeper(context: Context) {
    private val cm = context.getSystemService(ConnectivityManager::class.java)
    private val networks = HashMap<Network, NetworkCapabilities>()

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
            synchronized(networks) { networks[network] = caps }
            publish()
        }

        override fun onLost(network: Network) {
            synchronized(networks) { networks.remove(network) }
            publish()
        }
    }

    fun start() {
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        try {
            cm.requestNetwork(request, callback)
        } catch (_: RuntimeException) {
            // SecurityException without CHANGE_NETWORK_STATE, or too many requests: just watch.
            cm.registerNetworkCallback(request, callback)
        }
    }

    fun stop() {
        try {
            cm.unregisterNetworkCallback(callback)
        } catch (_: IllegalArgumentException) {
        }
        synchronized(networks) { networks.clear() }
        publish()
    }

    private fun publish() {
        val caps = synchronized(networks) { networks.values.toList() }
        _state.value = WifiState(
            connected = caps.isNotEmpty(),
            noInternet = caps.isNotEmpty() && caps.none { it.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) },
        )
    }

    companion object {
        private val _state = MutableStateFlow(WifiState())
        val state: StateFlow<WifiState> = _state.asStateFlow()
    }
}
