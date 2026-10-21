// Track drawing helpers from the desktop's core/track.py: the flat-earth constants and the scale bar length. Pure.

package com.lemongrass.aionav.core

import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.pow

object TrackMath {
    const val EARTH_R = 6378137.0
    /** Never zoom in further, so a parked vehicle does not plot its noise. */
    const val MIN_SPAN_M = 20.0

    /** The largest 1, 2 or 5 x 10^k not above x (scale bar length). */
    fun niceLength(x: Double): Double {
        val k = 10.0.pow(floor(log10(maxOf(x, 1e-9))))
        return if (x >= k) listOf(1.0, 2.0, 5.0).map { it * k }.filter { it <= x }.max() else k
    }
}
