package com.flipcam.camera

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.params.DynamicRangeProfiles
import android.hardware.camera2.params.OutputConfiguration
import android.hardware.camera2.params.SessionConfiguration
import android.util.Size
import android.view.Surface
import java.util.concurrent.Executor

/** Target capture spec: 4K60, 10-bit HLG (flat/Log-ish) HEVC. */
object VideoSpec {
    val SIZE = Size(3840, 2160)
    const val FPS = 60
    const val BITRATE = 100_000_000
    const val I_FRAME_INTERVAL = 1
}

/**
 * A selectable rear lens. [cameraId] is the id used to open a session; on the Xiaomi 15 Ultra
 * the logical back camera switches between ultrawide / 1" main / telephoto internally when the
 * stream sizes are supported, so ids may repeat across lens options.
 */
data class LensOption(
    val cameraId: String,
    val label: String,
    val focalLengthMm: Float,
    val isLogical: Boolean,
)

object CameraConfig {

    /** Best-effort rear-lens list, ordered ultrawide -> main -> telephoto. */
    fun discoverLenses(context: Context): List<LensOption> {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val found = mutableListOf<LensOption>()
        for (id in manager.cameraIdList) {
            val chars = runCatching { manager.getCameraCharacteristics(id) }.getOrNull() ?: continue
            val facing = chars.get(CameraCharacteristics.LENS_FACING) ?: continue
            if (facing != CameraCharacteristics.LENS_FACING_BACK) continue
            val focal = chars.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)
                ?.minOrNull() ?: 24f
            val caps = chars.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES) ?: intArrayOf()
            val logical = caps.contains(
                CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES_LOGICAL_MULTI_CAMERA
            )
            found += LensOption(id, labelFor(focal), focal, logical)
        }
        if (found.isEmpty()) {
            return listOf(LensOption("0", "1× MAIN", 23f, true))
        }
        return found.sortedBy { it.focalLengthMm }.distinctBy { it.focalLengthMm }
    }

    private fun labelFor(focalMm: Float): String = when {
        focalMm < 18f -> "0.5× UW"
        focalMm < 40f -> "1× MAIN"
        focalMm < 90f -> "3× TELE"
        else -> "5× TELE"
    }

    /** True when the camera advertises a 10-bit HLG output dynamic-range profile. */
    fun supportsHlg10(chars: CameraCharacteristics): Boolean {
        val profiles = chars.get(CameraCharacteristics.REQUEST_AVAILABLE_DYNAMIC_RANGE_PROFILES)
            ?: return false
        return profiles.supportedProfiles.contains(DynamicRangeProfiles.HLG10)
    }

    /**
     * Builds a regular session that renders preview through [previewTarget] and records into
     * [recordTarget], asking for the HLG10 dynamic range on the recording stream so the encoder
     * sees 10-bit BT.2020 HLG buffers.
     */
    fun buildSession(
        previewTarget: Surface,
        recordTarget: Surface,
        executor: Executor,
        callback: SessionConfiguration.StateCallback,
    ): SessionConfiguration {
        val previewConfig = OutputConfiguration(previewTarget)
        val recordConfig = OutputConfiguration(recordTarget).apply {
            setDynamicRangeProfile(DynamicRangeProfiles.HLG10)
        }
        return SessionConfiguration(
            SessionConfiguration.SESSION_REGULAR,
            listOf(previewConfig, recordConfig),
            executor,
            callback,
        )
    }
}
