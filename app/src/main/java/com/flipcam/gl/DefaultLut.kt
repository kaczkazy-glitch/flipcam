package com.flipcam.gl

/**
 * Bundled default look: a gentle filmic S-curve with teal shadows and warm highlights.
 * Generated in code so the APK needs no binary asset and no extra download.
 */
object DefaultLut {

    const val SIZE = 17

    fun build(): CubeLut {
        val n = SIZE
        val data = FloatArray(n * n * n * 3)
        var i = 0
        for (b in 0 until n) {
            for (g in 0 until n) {
                for (r in 0 until n) {
                    val rf = r / (n - 1f)
                    val gf = g / (n - 1f)
                    val bf = b / (n - 1f)

                    var cr = sCurve(rf)
                    var cg = sCurve(gf)
                    var cb = sCurve(bf)

                    val luma = 0.2126f * cr + 0.7152f * cg + 0.0722f * cb

                    // Lift shadows toward teal, cool them slightly.
                    val shadow = (1f - luma) * (1f - luma)
                    cr += 0.012f * shadow
                    cg += 0.040f * shadow
                    cb += 0.055f * shadow

                    // Warm and lightly compress the highlights.
                    val highlight = luma * luma * luma
                    cr += 0.055f * highlight
                    cg += 0.022f * highlight
                    cb -= 0.020f * highlight

                    data[i++] = cr.coerceIn(0f, 1f)
                    data[i++] = cg.coerceIn(0f, 1f)
                    data[i++] = cb.coerceIn(0f, 1f)
                }
            }
        }
        return CubeLut(n, data, "FlipCam Filmic")
    }

    private fun sCurve(x: Float): Float {
        val contrasted = (x - 0.5f) * 1.08f + 0.5f
        val t = contrasted.coerceIn(0f, 1f)
        return t * t * (3f - 2f * t)
    }
}
