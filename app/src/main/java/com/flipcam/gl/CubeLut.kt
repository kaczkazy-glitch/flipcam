package com.flipcam.gl

import android.content.Context
import android.net.Uri

/**
 * An RGB 3D LUT. [data] is laid out for a GL_TEXTURE_3D upload: red varies fastest, then green,
 * then blue, with three floats per entry in 0..1.
 */
class CubeLut(val size: Int, val data: FloatArray, val title: String = "") {

    init {
        require(size >= 2) { "LUT size must be >= 2" }
        require(data.size == size * size * size * 3) {
            "LUT data has ${data.size} floats, expected ${size * size * size * 3}"
        }
    }

    companion object {

        fun parse(text: String): CubeLut {
            var size = 0
            var title = "Untitled"
            val values = ArrayList<Float>(32 * 32 * 32 * 3)
            for (rawLine in text.lineSequence()) {
                val line = rawLine.substringBefore('#').trim()
                if (line.isEmpty()) continue
                val upper = line.uppercase()
                when {
                    upper.startsWith("TITLE") -> title = line.substringAfter("TITLE").trim().trim('"')
                    upper.startsWith("LUT_3D_SIZE") -> size = line.split(Regex("\\s+"))[1].toIntOrNull() ?: 0
                    upper.startsWith("LUT_1D_SIZE") -> return fromIdentity(17)
                    upper.startsWith("DOMAIN_MIN") || upper.startsWith("DOMAIN_MAX") -> Unit
                    else -> {
                        val parts = line.split(Regex("\\s+"))
                        if (parts.size >= 3) {
                            parts[0].toFloatOrNull()?.let { values.add(it) }
                            parts[1].toFloatOrNull()?.let { values.add(it) }
                            parts[2].toFloatOrNull()?.let { values.add(it) }
                        }
                    }
                }
            }
            if (size < 2) return fromIdentity(17)

            val expected = size * size * size * 3
            val out = FloatArray(expected)
            if (values.size >= expected) {
                for (i in 0 until expected) out[i] = values[i].coerceIn(0f, 1f)
            } else {
                // Pad a truncated file with the last complete entry rather than failing to load.
                var i = 0
                while (i < expected) {
                    out[i] = values.getOrElse(i) { 0f }.coerceIn(0f, 1f)
                    i++
                }
            }
            return CubeLut(size, out, title)
        }

        fun load(context: Context, uri: Uri): CubeLut? = runCatching {
            val text = context.contentResolver.openInputStream(uri)?.bufferedReader()
                ?.use { it.readText() } ?: return null
            parse(text)
        }.getOrNull()

        /** Neutral LUT, also the fallback for unreadable files. */
        fun fromIdentity(size: Int = 17): CubeLut {
            val data = FloatArray(size * size * size * 3)
            var i = 0
            for (b in 0 until size) {
                for (g in 0 until size) {
                    for (r in 0 until size) {
                        data[i++] = r / (size - 1f)
                        data[i++] = g / (size - 1f)
                        data[i++] = b / (size - 1f)
                    }
                }
            }
            return CubeLut(size, data, "Identity")
        }
    }
}
